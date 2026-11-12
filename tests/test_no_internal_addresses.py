"""Охоронець «жодних внутрішніх адрес»: репо Deai публічне, внутрішніх імен/адрес команди в ньому бути не може.

Дві частини.

1. Публічна (завжди): у файлі лише SHA-256 нормалізованих (нижній регістр) форм ВИСОКОентропійних значень
   (випадкові токени). Збіг — по ЦІЛОМУ токену `[A-Za-z0-9]+` відомої довжини, не по підрядку: `x<токен>` чи
   `<токен>x` знахідкою не є. Файли читаються цілком (без пропуску бінарних і великих), UTF-8 з errors='ignore';
   UTF-16 цей режим не бачить. Сирий токен не повертається й не друкується ніколи.
   Обмеження: у публічному файлі — лише хеші високоентропійних значень; низькоентропійні (домени, підмережі,
   короткі імена) живуть у зовнішньому списку мейнтейнера.

2. Зовнішній список (лише мейнтейнер/реліз): `DEAI_FORBIDDEN_LIST=<шлях>` — звичайний текст, одне значення
   на рядок. Кодування: UTF-8 (BOM дозволено) або UTF-16 (за BOM); суворо — недекодований файл це помилка.
   Коментар — лише рядок, що ПОЧИНАЄТЬСЯ з `#`; коментарі в кінці рядка НЕ підтримуються (значення з ` #`,
   NUL чи BOM усередині — помилка). Збіг — нечутливий до регістру ПІДРЯДОК (без токенізації, тож `x<значення>`
   і префікси ловляться). Скануються: (а) усі відстежувані git файли повними байтами (UTF-8 і UTF-16-LE, без
   пропуску бінарних/великих); (б) ІСТОРІЯ — усі blob-и, досяжні з `HEAD` і тегів релізів `v*` (рівно те, що публікується;
   локальні гілки не скануються), напряму через `git cat-file --batch` (не залежить від diff/textconv/`-diff`),
   метадані комітів (`git log` без diff: автор, комітер, повідомлення) та анотовані теги.
   Обмеження: UTF-16 — лише LE, а регістр там згортається лише для ASCII (кирилиця в UTF-16 — регістрово-чутлива).
   Звіт — лише `де:рядок:value#N` (N — індекс у списку, не значення), у stderr — `deai-forbidden: N values loaded`.
   Відстежуваний звичайний файл, що не читається (OSError, зламаний симлінк), РАХУЄТЬСЯ й валить тест;
   submodule (gitlink) лише перелічується як пропущений. Змінна задана, а файл відсутній/нечитний/порожній/
   некоректний — тест ПАДАЄ. Не задана — тест пропускається, КРІМ `DEAI_REQUIRE_FORBIDDEN_LIST=1`
   (релізний прогін): тоді відсутність списку теж падіння.

CLI:
  python3 tests/test_no_internal_addresses.py --scan ФАЙЛ...               # хеші: `шлях:рядок:word:хеш8`
  python3 tests/test_no_internal_addresses.py --list СПИСОК --scan ФАЙЛ... # список: `шлях:рядок:value#N`
Код виходу 1, якщо є знахідки. Без `--scan` працює як звичайний модуль `unittest`.
"""
import hashlib
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

WORDS = {
    '88eb2f7b8f2aedfc87c9a12e3b267380ca13d5931473f64a20d4300c5b7fb088',
    'b454075130549558aad6d40ee2cad779f84ac74be45845dcf3f0ee0c910ae00f',
}
WORD_LENGTHS = {20}
WORD_RE = re.compile(r'[A-Za-z0-9]+')
ENV_LIST = 'DEAI_FORBIDDEN_LIST'
ENV_REQUIRE = 'DEAI_REQUIRE_FORBIDDEN_LIST'
SHA_LINE = re.compile(rb'^[0-9a-f]{40}$')


class ForbiddenListError(Exception):
    pass


def _h(value):
    return hashlib.sha256(value.lower().encode('utf-8')).hexdigest()


# ---------- публічна частина: хеші ----------

def _read_text(path):
    """Текст файла цілком (UTF-8, errors='ignore') або None, якщо це не файл/не читається."""
    try:
        if not os.path.isfile(path):
            return None
        with open(path, 'rb') as f:
            data = f.read()
    except OSError:
        return None
    return data.decode('utf-8', errors='ignore')


def scan_detail(paths, words=WORDS, word_lengths=WORD_LENGTHS):
    """[(шлях, рядок, 'word', хеш)] — по одній на (рядок, хеш)."""
    out = []
    for path in paths:
        text = _read_text(path)
        if text is None:
            continue
        for no, line in enumerate(text.split('\n'), 1):
            seen = set()
            for m in WORD_RE.finditer(line):
                tok = m.group(0)
                if len(tok) in word_lengths:
                    h = _h(tok)
                    if h in words and h not in seen:
                        seen.add(h)
                        out.append((path, no, 'word', h))
    return out


def scan(paths, words=WORDS, word_lengths=WORD_LENGTHS):
    """[(шлях, рядок, вид)] — без сирого значення."""
    return [(p, n, k) for p, n, k, _ in scan_detail(paths, words, word_lengths)]


def tracked_files(repo=ROOT):
    out = subprocess.run(['git', 'ls-files', '-z'], cwd=repo, capture_output=True, check=True).stdout
    return [os.path.join(repo, p) for p in out.decode('utf-8', errors='ignore').split('\0') if p]


# ---------- зовнішній список (мейнтейнер) ----------

_INLINE_COMMENT = re.compile(r'\s#')


def _decode_list(raw):
    """Байти списку -> текст. UTF-16 (за BOM) або UTF-8 (BOM дозволено), суворо: сміття — помилка."""
    enc = 'utf-16' if raw[:2] in (b'\xff\xfe', b'\xfe\xff') else 'utf-8-sig'
    try:
        return raw.decode(enc)
    except UnicodeDecodeError:
        raise ForbiddenListError('зовнішній список не декодується як %s (%s)' % (enc, ENV_LIST))


def load_forbidden_list(path):
    """Значення зі списку (без коментарів і порожніх). Відсутній/нечитний/порожній/некоректний — ForbiddenListError.
    Коментар — лише рядок, що ПОЧИНАЄТЬСЯ з `#`; коментарі в кінці рядка не підтримуються (значення з ` #` —
    помилка, щоб «значення  # нотатка» не стало мовчки хибним значенням). Значення з NUL/BOM — теж помилка."""
    try:
        with open(path, 'rb') as f:
            raw = f.read()
    except OSError as e:
        raise ForbiddenListError('зовнішній список недоступний (%s): %s' % (ENV_LIST, e.strerror or type(e).__name__))
    values = []
    for no, line in enumerate(_decode_list(raw).splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '\x00' in line or '\ufeff' in line or _INLINE_COMMENT.search(line):
            raise ForbiddenListError('зовнішній список, рядок %d: NUL/BOM або коментар у кінці рядка (%s)' % (no, ENV_LIST))
        values.append(line)
    if not values:
        raise ForbiddenListError('зовнішній список порожній (%s)' % ENV_LIST)
    return values


def forbidden_values_from_env(env=os.environ):
    """None — змінна не задана (пропуск); список значень; або ForbiddenListError (реліз не пропускає мовчки).
    DEAI_REQUIRE_FORBIDDEN_LIST=1 без списку — теж ForbiddenListError. Друкує у stderr, скільки значень завантажено."""
    path = env.get(ENV_LIST)
    if not path:
        if env.get(ENV_REQUIRE) == '1':
            raise ForbiddenListError('%s=1, але %s не задано — релізну перевірку не можна пропускати' % (ENV_REQUIRE, ENV_LIST))
        return None
    values = load_forbidden_list(path)
    print('deai-forbidden: %d values loaded' % len(values), file=sys.stderr)
    return values


def _needles(values):
    """[(індекс, (utf-8, utf-16-le))] — обидві форми в нижньому регістрі."""
    out = []
    for i, v in enumerate(values):
        v = v.lower()
        if v:
            out.append((i, (v.encode('utf-8'), v.encode('utf-16-le'))))
    return out


def _lines_with(hay, needle, found):
    """Додає у found номери рядків (за b'\\n'), де needle зустрічається в hay."""
    pos, line, last = hay.find(needle), 1, 0
    while pos != -1:
        line += hay.count(b'\n', last, pos)  # наростаючий лічильник — без O(n²) на частих збігах
        last = pos
        found.add(line)
        pos = hay.find(needle, pos + 1)


def _match_bytes(data, needles):
    """[(рядок, індекс)]: UTF-8 (регістр Unicode) і UTF-16-LE (регістр лише ASCII)."""
    hay8 = data.decode('utf-8', errors='ignore').lower().encode('utf-8')
    hay16 = data.lower()
    out = []
    for i, (n8, n16) in needles:
        lines = set()
        _lines_with(hay8, n8, lines)
        _lines_with(hay16, n16, lines)
        out.extend((no, i) for no in sorted(lines))
    return out


def scan_files_external(paths, values, unreadable=None):
    """[(шлях, рядок, індекс_у_списку)] — підрядок без регістру; байти цілком, UTF-8 і UTF-16-LE.
    Файл, що не читається / не є звичайним файлом, додається в `unreadable` як (шлях, причина) — не мовчки."""
    needles = _needles(values)
    out = []
    for path in paths:
        try:
            if not os.path.isfile(path):
                if unreadable is not None:
                    unreadable.append((path, 'не звичайний файл (зламаний симлінк/відсутній)'))
                continue
            with open(path, 'rb') as f:
                data = f.read()
        except OSError as e:
            if unreadable is not None:
                unreadable.append((path, e.strerror or type(e).__name__))
            continue
        out.extend((path, no, i) for no, i in _match_bytes(data, needles))
    return out


def tracked_entries(repo=ROOT):
    """[(шлях, режим)] відстежуваних записів; режим 160000 — submodule (gitlink)."""
    raw = subprocess.run(['git', 'ls-files', '-z', '-s'], cwd=repo, capture_output=True, check=True).stdout
    out = []
    for rec in raw.decode('utf-8', errors='ignore').split('\0'):
        if rec:
            meta, _, path = rec.partition('\t')
            out.append((os.path.join(repo, path), meta.split(' ', 1)[0]))
    return out


def _stream_hits(cmd, repo, needles, where_of_line, out):
    """Потоково читає вивід git; where_of_line(рядок_у_байтах, поточне) -> нове «де» (або те саме)."""
    proc = subprocess.Popen(cmd, cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    where, no = None, 0
    try:
        for raw in proc.stdout:
            no += 1
            where = where_of_line(raw.rstrip(b'\r\n'), where)
            low = raw.decode('utf-8', errors='ignore').lower().encode('utf-8')
            for i, (n8, _n16) in needles:
                if n8 in low:
                    out.append((where or 'history', no, i))
    finally:
        proc.stdout.close()
        rc = proc.wait()
    if rc != 0:
        raise ForbiddenListError('git %s завершився з кодом %d' % (cmd[1], rc))


#: Публікуються лише `main` і теги релізів `v*` (пуш поіменно); локальні гілки й службові теги (бекапи) — ні.
PUBLISHED_TAGS = '--tags=v*'


def _scan_blobs(repo, needles, out):
    """Кожен blob, досяжний з `HEAD` і тегів `v*` (рівно те, що публікується), цілком: `blob@<sha10>`.
    Не залежить від diff/textconv/-diff/binary. Локальні гілки не скануються — вони не публікуються."""
    with tempfile.TemporaryFile() as lst:
        rl = subprocess.run(['git', 'rev-list', '--objects', 'HEAD', PUBLISHED_TAGS], cwd=repo, capture_output=True)
        if rl.returncode != 0:
            raise ForbiddenListError('git rev-list завершився з кодом %d' % rl.returncode)
        for line in rl.stdout.split(b'\n'):
            if line:
                lst.write(line.split(b' ', 1)[0] + b'\n')
        lst.seek(0)
        proc = subprocess.Popen(['git', 'cat-file', '--batch'], cwd=repo, stdin=lst,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            while True:
                head = proc.stdout.readline()
                if not head:
                    break
                parts = head.split()
                if len(parts) != 3:
                    raise ForbiddenListError('git cat-file: несподіваний рядок (об\'єкт відсутній?)')
                size = int(parts[2])
                data = proc.stdout.read(size)
                proc.stdout.read(1)
                if len(data) != size:
                    raise ForbiddenListError('git cat-file: обірваний потік')
                if parts[1] == b'blob':
                    where = 'blob@' + parts[0][:10].decode('ascii')
                    out.extend((where, no, i) for no, i in _match_bytes(data, needles))
                elif parts[1] == b'tree':
                    # Записи дерева = `<mode> <імʼя>\0<sha>`: імена файлів (і видалених) живуть лише тут — `rev-list`
                    # друкує кожен об'єкт один раз, тож blob з таким самим вмістом під іншим імʼям його не покаже.
                    where = 'path@' + parts[0][:10].decode('ascii')
                    out.extend((where, 1, i) for _, i in _match_bytes(data, needles))
        finally:
            proc.stdout.close()
            rc = proc.wait()
        if rc != 0:
            raise ForbiddenListError('git cat-file завершився з кодом %d' % rc)


def scan_repo_external(values, repo=ROOT, report=None):
    """[(де, рядок, індекс)]: відстежувані файли, blob-и історії (`blob@sha`), імена в деревах історії (`path@sha` — sha дерева), метадані комітів (`history@sha`),
    анотовані теги (`tag:ref`). `report` (dict) отримує `unreadable` і `skipped` [(шлях, причина)]."""
    needles = _needles(values)
    unreadable, skipped, paths = [], [], []
    for path, mode in tracked_entries(repo):
        if mode == '160000':
            skipped.append((path, 'submodule'))
        else:
            paths.append(path)
    out = scan_files_external(paths, values, unreadable)
    if report is not None:
        report['unreadable'], report['skipped'] = unreadable, skipped

    def commit_of(line, cur):
        return 'history@' + line[:10].decode('ascii') if SHA_LINE.match(line) else cur

    def tag_of(line, cur):
        return 'tag:' + line.split(b' ', 1)[0].decode('utf-8', errors='ignore') if line.startswith(b'refs/tags/') else cur

    # метадані комітів (автор/комітер/повідомлення) — без diff; вміст ловить прохід по blob-ах
    _stream_hits(['git', '-c', 'core.quotepath=off', 'log', '--no-color', '--text', '--no-textconv', '--no-ext-diff',
                  '-m', '--format=%H%n%an <%ae>%n%cn <%ce>%n%B', 'HEAD', PUBLISHED_TAGS],
                 repo, needles, commit_of, out)
    _scan_blobs(repo, needles, out)
    _stream_hits(['git', 'for-each-ref', 'refs/tags/v*',
                  '--format=%(refname) %(taggername) %(taggeremail)%0a%(contents)'],
                 repo, needles, tag_of, out)
    return out


def external_problems(values, repo=ROOT):
    """Список проблем (порожній — все гаразд): знахідки та нечитні відстежувані файли. Submodule — лише skipped."""
    report = {}
    hits = scan_repo_external(values, repo=repo, report=report)
    problems = []
    if hits:
        problems.append('значення зовнішнього списку у файлах/історії:\n' +
                        '\n'.join('%s:%d:value#%d' % (os.path.relpath(h[0], repo) if os.path.isabs(h[0]) else h[0], h[1], h[2])
                                  for h in hits))
    if report['unreadable']:
        problems.append('unreadable: %d відстежуваних файлів не прочитано:\n' % len(report['unreadable']) +
                        '\n'.join('%s (%s)' % (os.path.relpath(p, repo), why) for p, why in report['unreadable']))
    for p, why in report['skipped']:
        print('deai-forbidden: пропущено %s (%s)' % (os.path.relpath(p, repo), why), file=sys.stderr)
    return problems


class NoInternalAddresses(unittest.TestCase):
    def test_tracked_files_have_no_internal_addresses(self):
        files = tracked_files()
        self.assertTrue(files, '`git ls-files` повернув порожній список — перевірка нічого не перевірила')
        hits = scan(files)
        listing = '\n'.join('%s:%d:%s' % (os.path.relpath(p, ROOT), n, k) for p, n, k in hits)
        self.assertEqual(hits, [], 'внутрішні адреси у відстежуваних файлах:\n' + listing)

    def test_external_list_finds_nothing_in_repo_and_history(self):
        try:
            values = forbidden_values_from_env()
        except ForbiddenListError as e:
            self.fail(str(e))
        if values is None:
            self.skipTest('DEAI_FORBIDDEN_LIST не задано — зовнішній список перевіряє лише релізний прогін')
        self.assertEqual(external_problems(values), [])


# ---------- самоперевірки ----------

_GIT_ENV = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)


def _git(repo, *args, user='tester', email='tester@example.invalid'):
    return subprocess.run(
        ['git', '-c', 'user.name=' + user, '-c', 'user.email=' + email,
         '-c', 'commit.gpgsign=false', '-c', 'tag.gpgsign=false'] + list(args),
        cwd=repo, env=_GIT_ENV, check=True, capture_output=True)


class HashedScannerSelfTest(unittest.TestCase):
    """Хеш-сканер без справжніх значень: «канарка» збирається в рантаймі, її хеш підміняє WORDS."""
    WORD = 'canary' + 'tokenxyz'        # 14 знаків

    def _dir(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        return d.name

    def _file(self, text, raw=None):
        p = os.path.join(self._dir(), 'f.txt')
        with open(p, 'wb') as f:
            f.write(raw if raw is not None else text.encode('utf-8'))
        return p

    def _scan(self, p, **kw):
        base = dict(words={_h(self.WORD)}, word_lengths={len(self.WORD)})
        base.update(kw)
        return scan([p], **base)

    def test_builtin_set_is_only_the_two_high_entropy_hashes(self):
        self.assertEqual(len(WORDS), 2)
        self.assertEqual(WORD_LENGTHS, {20})

    def test_word_hit_with_line_number(self):
        p = self._file('нічого\nтут %s є\nі далі\n' % self.WORD)
        self.assertEqual(self._scan(p), [(p, 2, 'word')])

    def test_word_is_case_insensitive(self):
        self.assertEqual(len(self._scan(self._file('x CanaryTokenXYZ y'))), 1)

    def test_word_is_whole_token_not_substring(self):
        for text in ('x%s' % self.WORD, '%sx' % self.WORD, 'a%s_b' % self.WORD):
            self.assertEqual(self._scan(self._file(text)), [], text)
        self.assertEqual(len(self._scan(self._file('a-%s_b' % self.WORD))), 1)

    def test_word_length_prefilter(self):
        self.assertEqual(self._scan(self._file('x %s y' % self.WORD), word_lengths={3}), [])

    def test_result_never_carries_the_raw_token(self):
        p = self._file('x %s y' % self.WORD)
        detail = scan_detail([p], words={_h(self.WORD)}, word_lengths={len(self.WORD)})
        self.assertNotIn(self.WORD, repr(detail))

    def test_file_with_nul_is_scanned(self):
        p = self._file('', raw=b'\x00\x01 ' + self.WORD.encode() + b' \x00')
        self.assertEqual(len(self._scan(p)), 1)

    def test_big_file_is_scanned(self):
        p = self._file('', raw=b'a\n' * (3 * 1024 * 1024) + b'\n' + self.WORD.encode() + b'\n')
        self.assertGreater(os.path.getsize(p), 5 * 1024 * 1024)
        self.assertEqual(len(self._scan(p)), 1)

    def test_missing_file_is_skipped(self):
        self.assertEqual(self._scan(os.path.join(self._dir(), 'nope')), [])

    def test_untracked_file_is_not_in_the_tracked_list(self):
        self.assertNotIn(self._file('x'), tracked_files())

    def test_empty_repo_has_no_tracked_files(self):
        repo = self._dir()
        _git(repo, 'init', '-q')
        self.assertEqual(tracked_files(repo), [])


class ExternalListSelfTest(unittest.TestCase):
    """Зовнішній режим: список і тимчасове git-репо збираються в рантаймі (канарки), реальне репо не чіпаємо."""
    CANARY = 'zq' + 'internal' + 'canary'
    OTHER = 'zq' + 'another' + 'canary'

    def _dir(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        return d.name

    def _list(self, text):
        p = os.path.join(self._dir(), 'list.txt')
        with open(p, 'w', encoding='utf-8') as f:
            f.write(text)
        return p

    def _repo(self):
        repo = self._dir()
        _git(repo, 'init', '-q')
        return repo

    def _write(self, repo, name, data):
        with open(os.path.join(repo, name), 'wb') as f:
            f.write(data if isinstance(data, bytes) else data.encode('utf-8'))

    def _commit(self, repo, msg='m', **kw):
        _git(repo, 'add', '-A')
        _git(repo, 'commit', '-q', '-m', msg, **kw)

    def _scan(self, repo, values=None):
        return scan_repo_external(values or [self.CANARY], repo=repo)

    def _wheres(self, hits):
        return sorted(h[0] for h in hits)

    # --- список ---
    def test_load_list_skips_comments_and_blanks(self):
        p = self._list('# коментар\n\n  %s  \n#ще\n%s\n' % (self.CANARY, self.OTHER))
        self.assertEqual(load_forbidden_list(p), [self.CANARY, self.OTHER])

    def test_load_list_missing_raises(self):
        with self.assertRaises(ForbiddenListError):
            load_forbidden_list(os.path.join(self._dir(), 'nope.txt'))

    def test_load_list_empty_raises(self):
        with self.assertRaises(ForbiddenListError):
            load_forbidden_list(self._list('# лише коментар\n\n'))

    def test_env_set_with_missing_file_fails_not_skips(self):
        with self.assertRaises(ForbiddenListError):
            forbidden_values_from_env({ENV_LIST: os.path.join(self._dir(), 'nope.txt')})

    def test_env_set_with_empty_file_fails(self):
        with self.assertRaises(ForbiddenListError):
            forbidden_values_from_env({ENV_LIST: self._list('')})

    def test_env_unset_means_skip(self):
        self.assertIsNone(forbidden_values_from_env({}))

    def test_env_set_returns_values(self):
        self.assertEqual(forbidden_values_from_env({ENV_LIST: self._list(self.CANARY + '\n')}), [self.CANARY])

    def _list_raw(self, raw):
        p = os.path.join(self._dir(), 'list.bin')
        with open(p, 'wb') as f:
            f.write(raw)
        return p

    def test_load_list_utf8_bom_keeps_first_value(self):
        p = self._list_raw(b'\xef\xbb\xbf' + (self.CANARY + '\n' + self.OTHER + '\n').encode('utf-8'))
        self.assertEqual(load_forbidden_list(p), [self.CANARY, self.OTHER])

    def test_load_list_utf16_with_bom_le_and_be(self):
        text = '# c\n%s\n%s\n' % (self.CANARY, self.OTHER)
        le = self._list_raw(b'\xff\xfe' + text.encode('utf-16-le'))
        be = self._list_raw(b'\xfe\xff' + text.encode('utf-16-be'))
        self.assertEqual(load_forbidden_list(le), [self.CANARY, self.OTHER])
        self.assertEqual(load_forbidden_list(be), [self.CANARY, self.OTHER])

    def test_load_list_invalid_utf8_raises(self):
        with self.assertRaises(ForbiddenListError):
            load_forbidden_list(self._list_raw((self.CANARY + '\n').encode('utf-8') + b'\xd0\n'))

    def test_load_list_inline_comment_raises_without_leaking_value(self):
        for sep in ('  # note', ' #note', '\t# note'):
            with self.assertRaises(ForbiddenListError) as cm:
                load_forbidden_list(self._list('%s%s\n' % (self.CANARY, sep)))
            self.assertNotIn(self.CANARY, str(cm.exception).lower())

    def test_load_list_hash_inside_value_without_space_is_allowed(self):
        self.assertEqual(load_forbidden_list(self._list('a#b\n')), ['a#b'])

    def test_load_list_nul_or_inner_bom_raises(self):
        for raw in ((self.CANARY + '\x00\n').encode(), ('ok\n\ufeff' + self.CANARY + '\n').encode('utf-8')):
            with self.assertRaises(ForbiddenListError):
                load_forbidden_list(self._list_raw(raw))

    def test_env_set_reports_count_on_stderr(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            forbidden_values_from_env({ENV_LIST: self._list('%s\n%s\n' % (self.CANARY, self.OTHER))})
        self.assertEqual(buf.getvalue().strip(), 'deai-forbidden: 2 values loaded')

    def test_require_flag_without_list_fails(self):
        with self.assertRaises(ForbiddenListError):
            forbidden_values_from_env({ENV_REQUIRE: '1'})
        self.assertIsNone(forbidden_values_from_env({ENV_REQUIRE: '0'}))

    def test_require_flag_end_to_end_test_fails_not_skips(self):
        env = {k: v for k, v in _GIT_ENV.items() if k not in (ENV_LIST, ENV_REQUIRE)}
        env[ENV_REQUIRE] = '1'
        r = subprocess.run([sys.executable, '-B', '-m', 'unittest',
                            'tests.test_no_internal_addresses.NoInternalAddresses.'
                            'test_external_list_finds_nothing_in_repo_and_history'],
                           cwd=ROOT, env=env, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0, r.stderr)
        self.assertNotIn('skipped', r.stderr)

    # --- файли ---
    def test_tracked_file_hit_case_insensitive_with_line_and_index(self):
        repo = self._repo()
        self._write(repo, 'a.txt', 'один\nдва %s три\n' % self.CANARY.upper())
        self._commit(repo)
        hits = scan_repo_external([self.OTHER, self.CANARY], repo=repo)
        files = [h for h in hits if h[0].endswith('a.txt')]
        self.assertEqual([(os.path.relpath(w, repo), n, i) for w, n, i in files], [('a.txt', 2, 1)])

    def test_value_glued_to_letters_is_found(self):
        repo = self._repo()
        self._write(repo, 'a.txt', 'x%sy\n' % self.CANARY)
        self._commit(repo)
        self.assertTrue([h for h in self._scan(repo) if h[0].endswith('a.txt')])

    def test_utf16le_file_is_found(self):
        repo = self._repo()
        self._write(repo, 'u.txt', ('перший\nтут %s є\n' % self.CANARY).encode('utf-16-le'))
        self._commit(repo)
        hits = [h for h in self._scan(repo) if h[0].endswith('u.txt')]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0][1], 2)

    def test_binary_with_nul_and_big_file_not_skipped(self):
        repo = self._repo()
        self._write(repo, 'b.bin', b'\x00\x01' + self.CANARY.encode() + b'\x00')
        self._write(repo, 'big.txt', b'a\n' * (3 * 1024 * 1024) + self.CANARY.encode() + b'\n')
        self._commit(repo)
        hits = self._scan(repo)
        self.assertTrue([h for h in hits if h[0].endswith('b.bin')])
        self.assertTrue([h for h in hits if h[0].endswith('big.txt')])

    # --- історія ---
    def test_removed_value_is_still_found_in_history(self):
        repo = self._repo()
        self._write(repo, 'a.txt', 'секрет %s\n' % self.CANARY)
        self._commit(repo, 'додав')
        os.remove(os.path.join(repo, 'a.txt'))
        self._write(repo, 'b.txt', 'чисто\n')
        self._commit(repo, 'прибрав')
        hits = self._scan(repo)
        self.assertFalse([h for h in hits if not h[0].startswith(('history', 'tag', 'blob@'))])
        self.assertTrue([h for h in hits if h[0].startswith('blob@')])

    def test_value_in_author_email_is_found(self):
        repo = self._repo()
        self._write(repo, 'a.txt', 'чисто\n')
        self._commit(repo, 'm', email='%s@example.invalid' % self.CANARY)
        self.assertTrue([h for h in self._scan(repo) if h[0].startswith('history')])

    def test_value_in_commit_message_is_found(self):
        repo = self._repo()
        self._write(repo, 'a.txt', 'чисто\n')
        self._commit(repo, 'про %s' % self.CANARY)
        self.assertTrue([h for h in self._scan(repo) if h[0].startswith('history')])

    def test_history_match_is_case_insensitive(self):
        repo = self._repo()
        self._write(repo, 'a.txt', 'чисто\n')
        self._commit(repo, 'про %s' % self.CANARY.upper())
        self.assertTrue([h for h in self._scan(repo) if h[0].startswith('history')])

    def test_utf16le_match_is_case_insensitive(self):
        repo = self._repo()
        self._write(repo, 'u.txt', ('тут %s\n' % self.CANARY.upper()).encode('utf-16-le'))
        self._commit(repo)
        self.assertTrue([h for h in self._scan(repo) if h[0].endswith('u.txt')])

    def test_value_in_annotated_tag_message_is_found(self):
        repo = self._repo()
        self._write(repo, 'a.txt', 'чисто\n')
        self._commit(repo)
        _git(repo, 'tag', '-a', 'v1', '-m', 'реліз %s' % self.CANARY)
        hits = self._scan(repo)
        self.assertTrue([h for h in hits if h[0].startswith('tag')])
        self.assertFalse([h for h in hits if h[0].startswith('history')])

    def test_blob_in_no_diff_file_is_found_in_history(self):
        repo = self._repo()
        self._write(repo, '.gitattributes', '*.dat -diff\n*.bin binary\n')
        self._write(repo, 'x.dat', 'дані %s\n' % self.CANARY)
        self._write(repo, 'y.bin', b'\x00\x01' + self.CANARY.encode() + b'\x00')
        self._commit(repo, 'додав')
        os.remove(os.path.join(repo, 'x.dat'))
        os.remove(os.path.join(repo, 'y.bin'))
        self._commit(repo, 'прибрав')
        hits = self._scan(repo)
        self.assertEqual(len([h for h in hits if h[0].startswith('blob@')]), 2, hits)

    def test_value_only_in_a_deleted_file_name_is_found(self):
        repo = self._repo()
        os.makedirs(os.path.join(repo, 'docs'))
        self._write(repo, 'docs/%s-notes.txt' % self.CANARY, 'чисто\n')
        self._write(repo, 'keep.txt', 'чисто\n')
        self._commit(repo, 'додав')
        os.remove(os.path.join(repo, 'docs', '%s-notes.txt' % self.CANARY))
        self._commit(repo, 'прибрав')
        hits = [h for h in self._scan(repo) if h[0].startswith('path@')]
        self.assertTrue(hits, self._scan(repo))

    def test_line_numbers_of_many_hits_are_right(self):
        repo = self._repo()
        self._write(repo, 'm.txt', ''.join('%s\n' % (self.CANARY if k % 3 == 0 else 'x') for k in range(1, 10)))
        self._commit(repo)
        hits = sorted(h[1] for h in self._scan(repo) if h[0].endswith('m.txt'))
        self.assertEqual(hits, [3, 6, 9])

    def test_utf16le_blob_removed_from_history_is_found(self):
        repo = self._repo()
        self._write(repo, 'u.txt', ('x\n%s\n' % self.CANARY).encode('utf-16-le'))
        self._commit(repo)
        os.remove(os.path.join(repo, 'u.txt'))
        self._commit(repo, 'прибрав')
        hits = [h for h in self._scan(repo) if h[0].startswith('blob@')]
        self.assertEqual(len(hits), 1, hits)

    def _side_commit_with_tag(self, repo, tag_args):
        _git(repo, 'branch', '-m', 'main')
        self._write(repo, 'a.txt', 'чисто\n')
        self._commit(repo)
        _git(repo, 'checkout', '-q', '-b', 'side')
        self._write(repo, 'side.txt', '%s\n' % self.CANARY)
        self._commit(repo, 'бічна')
        if tag_args:
            _git(repo, 'tag', *tag_args)
        _git(repo, 'checkout', '-q', 'main')
        _git(repo, 'branch', '-D', 'side')

    def test_value_only_in_tag_tree_outside_head_is_found(self):
        repo = self._repo()
        self._side_commit_with_tag(repo, ['v9.9.9'])
        self.assertTrue([h for h in self._scan(repo) if h[0].startswith('blob@')])

    def test_unpublished_non_release_tags_are_not_scanned(self):
        # публікуються лише теги релізів `v*`; локальний резервний тег (напр. бекап до переписування історії) нікуди не йде
        repo = self._repo()
        self._side_commit_with_tag(repo, ['-a', 'backup-x', '-m', 'бекап %s' % self.CANARY])
        self.assertEqual(self._scan(repo), [])

    def test_commit_message_only_on_tagged_side_commit_is_found(self):
        repo = self._repo()
        _git(repo, 'branch', '-m', 'main')
        self._write(repo, 'a.txt', 'чисто\n')
        self._commit(repo)
        _git(repo, 'checkout', '-q', '-b', 'side')
        self._write(repo, 's.txt', 'чисто2\n')
        self._commit(repo, 'про %s' % self.CANARY)
        _git(repo, 'tag', 'v9.9.9')
        _git(repo, 'checkout', '-q', 'main')
        _git(repo, 'branch', '-D', 'side')
        self.assertTrue([h for h in self._scan(repo) if h[0].startswith('history@')])

    def test_value_only_on_unpublished_local_branch_is_not_scanned(self):
        # публікується лише HEAD + теги; локальні гілки нікуди не йдуть
        repo = self._repo()
        _git(repo, 'branch', '-m', 'main')
        self._write(repo, 'a.txt', 'чисто\n')
        self._commit(repo)
        _git(repo, 'checkout', '-q', '-b', 'wip')
        self._write(repo, 'w.txt', '%s\n' % self.CANARY)
        self._commit(repo, 'wip')
        _git(repo, 'checkout', '-q', 'main')
        self.assertEqual(self._scan(repo), [])

    def test_value_in_merge_result_is_found(self):
        repo = self._repo()
        _git(repo, 'branch', '-m', 'main')
        self._write(repo, 'a.txt', 'чисто\n')
        self._commit(repo)
        _git(repo, 'checkout', '-q', '-b', 'f')
        self._write(repo, 'f.txt', '%s\n' % self.CANARY)
        self._commit(repo, 'f')
        _git(repo, 'checkout', '-q', 'main')
        self._write(repo, 'm.txt', 'інше\n')
        self._commit(repo, 'm')
        _git(repo, 'merge', '-q', '--no-ff', '-m', 'злиття', 'f')
        self.assertTrue([h for h in self._scan(repo) if h[0].startswith('blob@')])

    # --- нечитні файли ---
    def test_unreadable_tracked_file_is_counted_and_fails(self):
        if hasattr(os, 'geteuid') and os.geteuid() == 0:
            self.skipTest('root читає будь-який файл')
        repo = self._repo()
        self._write(repo, 'a.txt', 'чисто\n')
        self._write(repo, 'locked.txt', 'x\n')
        self._commit(repo)
        path = os.path.join(repo, 'locked.txt')
        os.chmod(path, 0)
        self.addCleanup(os.chmod, path, 0o600)
        report = {}
        scan_repo_external([self.CANARY], repo=repo, report=report)
        self.assertEqual([os.path.relpath(p, repo) for p, _ in report['unreadable']], ['locked.txt'])
        problems = external_problems([self.CANARY], repo=repo)
        self.assertTrue([m for m in problems if 'unreadable' in m], problems)

    def test_broken_symlink_and_missing_tracked_file_count_as_unreadable(self):
        repo = self._repo()
        os.symlink('nope-target', os.path.join(repo, 'ln'))
        self._write(repo, 'gone.txt', 'x\n')
        self._commit(repo)
        os.remove(os.path.join(repo, 'gone.txt'))
        report = {}
        scan_repo_external([self.CANARY], repo=repo, report=report)
        self.assertEqual(sorted(os.path.relpath(p, repo) for p, _ in report['unreadable']), ['gone.txt', 'ln'])

    def test_submodule_entry_is_skipped_with_reason_not_failed(self):
        repo = self._repo()
        self._write(repo, 'a.txt', 'чисто\n')
        self._commit(repo)
        _git(repo, 'update-index', '--add', '--cacheinfo', '160000,' + '1' * 40 + ',sub')
        _git(repo, 'commit', '-q', '-m', 'sub')
        report = {}
        scan_repo_external([self.CANARY], repo=repo, report=report)
        self.assertEqual(report['unreadable'], [])
        self.assertEqual([(os.path.relpath(p, repo), why) for p, why in report['skipped']], [('sub', 'submodule')])
        self.assertEqual(external_problems([self.CANARY], repo=repo), [])

    def test_clean_repo_has_no_hits(self):
        repo = self._repo()
        self._write(repo, 'a.txt', 'чисто\n')
        self._commit(repo)
        _git(repo, 'tag', '-a', 'v1', '-m', 'реліз')
        self.assertEqual(self._scan(repo), [])

    def test_report_never_carries_the_raw_value(self):
        repo = self._repo()
        self._write(repo, 'a.txt', '%s\n' % self.CANARY)
        self._commit(repo, 'про %s' % self.CANARY)
        _git(repo, 'tag', '-a', 'v1', '-m', self.CANARY)
        hits = self._scan(repo)
        self.assertTrue(hits)
        self.assertNotIn(self.CANARY, repr(hits).lower())

    # --- CLI ---
    def _cli(self, *args):
        return subprocess.run([sys.executable, '-B', os.path.abspath(__file__)] + list(args),
                              capture_output=True, text=True, env=_GIT_ENV)

    def test_cli_list_scan_reports_path_line_index(self):
        lst = self._list('# c\nxx-not-here\n%s\n' % self.CANARY)
        f = os.path.join(self._dir(), 'f.txt')
        with open(f, 'w') as fh:
            fh.write('a\nb %s\n' % self.CANARY)
        r = self._cli('--list', lst, '--scan', f)
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertEqual(r.stdout.strip(), '%s:2:value#1' % f)
        self.assertNotIn(self.CANARY, r.stdout + r.stderr)

    def test_cli_list_scan_clean_exits_zero(self):
        lst = self._list(self.CANARY + '\n')
        f = os.path.join(self._dir(), 'f.txt')
        with open(f, 'w') as fh:
            fh.write('нічого\n')
        r = self._cli('--list', lst, '--scan', f)
        self.assertEqual((r.returncode, r.stdout), (0, ''))

    def test_cli_list_scan_reports_loaded_count_on_stderr(self):
        lst = self._list('%s\n%s\n' % (self.CANARY, self.OTHER))
        f = os.path.join(self._dir(), 'f.txt')
        with open(f, 'w') as fh:
            fh.write('нічого\n')
        r = self._cli('--list', lst, '--scan', f)
        self.assertEqual(r.returncode, 0)
        self.assertIn('deai-forbidden: 2 values loaded', r.stderr)

    def test_cli_list_scan_unreadable_file_is_an_error(self):
        lst = self._list(self.CANARY + '\n')
        r = self._cli('--list', lst, '--scan', os.path.join(self._dir(), 'nope'))
        self.assertEqual(r.returncode, 2)

    def test_cli_list_missing_file_is_an_error(self):
        f = os.path.join(self._dir(), 'f.txt')
        open(f, 'w').close()
        r = self._cli('--list', os.path.join(self._dir(), 'nope'), '--scan', f)
        self.assertEqual(r.returncode, 2)

    def test_cli_hash_scan_still_works(self):
        f = os.path.join(self._dir(), 'f.txt')
        with open(f, 'w') as fh:
            fh.write('нічого\n')
        r = self._cli('--scan', f)
        self.assertEqual((r.returncode, r.stdout), (0, ''))


def _main(argv):
    lst = None
    if argv and argv[0] == '--list':
        if len(argv) < 2:
            print('usage: --list СПИСОК --scan ФАЙЛ...', file=sys.stderr)
            return 2
        lst, argv = argv[1], argv[2:]
    if not argv or argv[0] != '--scan' or len(argv) < 2:
        print('usage: test_no_internal_addresses.py [--list СПИСОК] --scan ФАЙЛ...', file=sys.stderr)
        return 2
    files = argv[1:]
    if lst is not None:
        try:
            values = load_forbidden_list(lst)
        except ForbiddenListError as e:
            print(e, file=sys.stderr)
            return 2
        print('deai-forbidden: %d values loaded' % len(values), file=sys.stderr)
        unreadable = []
        hits = scan_files_external(files, values, unreadable)
        for p, n, i in hits:
            print('%s:%d:value#%d' % (p, n, i))
        for p, why in unreadable:
            print('unreadable: %s (%s)' % (p, why), file=sys.stderr)
        if unreadable:
            return 2
        return 1 if hits else 0
    hits = scan_detail(files)
    for p, n, k, h in hits:
        print('%s:%d:%s:%s' % (p, n, k, h[:8]))
    return 1 if hits else 0


if __name__ == '__main__':
    args = sys.argv[1:]
    if args and args[0] in ('--scan', '--list'):
        sys.exit(_main(args))
    unittest.main()
