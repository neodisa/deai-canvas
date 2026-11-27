# Лендинг, Pages, Releases — частина A: план реалізації

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** лендинг Deai Canvas лежить у репо й публікується на GitHub Pages; кожен тег `vX.Y.Z` отримує GitHub Release з
текстом із CHANGELOG; README і сайт показують два шляхи встановлення й як підключити свого агента.

**Architecture:** статичний `landing/` (HTML/CSS/vanilla JS, без збирача). Два stdlib-скрипти в `ops/`: `release_notes.py`
(секція CHANGELOG → текст Release) і `build_site.py` (копія `landing/` → `_site/` з версією в футері). Два workflow у
`.github/workflows/`: `release.yml` (тег → Release) і `pages.yml` (main/Release → Pages). Код застосунку (`app/`), `CHANGELOG.md`
і версія в `package.json` НЕ змінюються.

**Tech Stack:** HTML/CSS/JS без залежностей, Python 3.9+ stdlib + `unittest`, Node 20+ + Playwright (лише скрипти знімків),
GitHub Actions (`actions/checkout@v7`, `actions/configure-pages@v6`, `actions/upload-pages-artifact@v5`, `actions/deploy-pages@v5`).

**Spec:** `docs/superpowers/specs/2026-11-25-landing-releases-design.md` (частина A).

---

## Правила для виконавця (обовʼязкові)

- Працюй лише в цьому worktree. Живий чекаут власника (`git rev-parse --git-common-dir` → його `..`) — ЛИШЕ читати.
- Не чіпай `app/`, `CHANGELOG.md`, `package.json`, порти 8765/4317, `~/.deai`, `~/deai-work`, `~/deai-published`.
- `python3 -B` завжди. Без `rm -rf`, без `pkill`/`killall` за шаблоном, без мережевих установок.
- Коміт ЛИШЕ так (нові файли спершу `git add -- <path>`; ніколи `git add -A`, `reset`, `rebase`, `--amend`, `stash`):
  ```bash
  git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "<тема>" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- <шляхи>
  ```
- Ніколи не стейдж `docs/superpowers/specs/2026-10-20-agents-in-canvas-design.md`,
  `docs/superpowers/specs/2026-11-09-agents-sdk-policy-addendum.md`, `.claude/`.
- Перед кожним комітом — тест внутрішніх адрес (бачить лише tracked-файли, тому після `git add`):
  ```bash
  DEAI_FORBIDDEN_LIST="$HOME/Liga Tools/design-office-transition/scripts/deai-forbidden.txt" DEAI_REQUIRE_FORBIDDEN_LIST=1 python3 -B -m unittest tests.test_no_internal_addresses
  ```
  Очікування: `OK`. У файлах — жодних імен людей, абсолютних локальних шляхів, внутрішніх хостів.
- Перегляд лендинга: `python3 -B -m http.server 8087 --bind 127.0.0.1 --directory landing` (у фоні; зупиняти за PID).

## Файли

| Файл | Що робить |
|---|---|
| `landing/index.html`, `styles.css`, `site.js` | сторінка; `site.js` — вкладки, лайтбокс, копіювання, меню, Share |
| `landing/README.md` | як переглядати, збирати й перезнімати |
| `landing/assets/*` | WebP-знімки 2880 px, іконка, шрифт + OFL, `og.png` |
| `ops/landing-shots.mjs`, `ops/landing-shots/*` | перезйомка знімків продукту на вигаданих демо |
| `ops/landing-og.mjs` | рендер `landing/assets/og.png` 1200×630 |
| `ops/release_notes.py` + `tests/test_release_notes.py` | текст Release з CHANGELOG |
| `ops/build_site.py` + `tests/test_build_site.py` | `_site/` для Pages з версією |
| `.github/workflows/release.yml`, `pages.yml` | автоматизація |
| `README.md` | «Get started», «Connect your agent», посилання на сайт |

---

### Task 1: Лендинг у репо як є, без PNG-оригіналів

**Files:**
- Create: `landing/index.html`, `landing/styles.css`, `landing/site.js`, `landing/README.md`, `landing/assets/*`,
  `ops/landing-shots.mjs`, `ops/landing-shots/*`
- Modify (після копіювання): `landing/index.html`, `ops/landing-shots.mjs`, `landing/README.md`

- [ ] **Step 1: Скопіювати з живого чекауту (без `landing/screenshots/`)**

```bash
MAIN="$(cd "$(git rev-parse --git-common-dir)/.." && pwd)"
mkdir -p landing/assets ops/landing-shots
cp "$MAIN"/landing/index.html "$MAIN"/landing/styles.css "$MAIN"/landing/site.js "$MAIN"/landing/README.md landing/
cp "$MAIN"/landing/assets/* landing/assets/
cp "$MAIN"/ops/landing-shots.mjs ops/
cp "$MAIN"/ops/landing-shots/* ops/landing-shots/
ls landing landing/assets ops/landing-shots
```
Очікування: `landing/` без теки `screenshots`; в `assets/` 6 `.webp`, `deai-icon.png`, `rethink-sans.woff2`, `rethink-sans-OFL.txt`.

- [ ] **Step 2: Посилання на знімки — на WebP, «Full-size PNG» → «Full size»**

```bash
python3 -B - <<'EOF'
import re
p = 'landing/index.html'
s = open(p, encoding='utf-8').read()
s, n = re.subn(r'href="screenshots/([a-z-]+)\.png"', r'href="assets/\1.webp"', s)
assert n == 7, n
s = s.replace('Full-size PNG <span aria-hidden="true">↗</span>', 'Full size <span aria-hidden="true">↗</span>')
open(p, 'w', encoding='utf-8').write(s)
EOF
grep -c 'screenshots/' landing/index.html
python3 -B -c "import re,os;s=open('landing/index.html').read();m=re.findall(r'(?:href|src)=\"(assets/[^\"]+)\"',s);print([x for x in m if not os.path.exists('landing/'+x)])"
```
Очікування: `0`, потім `[]`.

- [ ] **Step 3: Скрипт знімків більше не кладе PNG у `landing/`**

У `ops/landing-shots.mjs` видалити рядок
```js
  copyFileSync(png, path.join(root, "landing/screenshots", `${name}.png`));
```
і рядок
```js
  mkdirSync(path.join(root, "landing/screenshots"), { recursive: true });
```
а `console.log(\`${name}.png\`);` замінити на `console.log(\`${name}.webp\`);`. Перевірка: `grep -n "screenshots" ops/landing-shots.mjs` — порожньо.

- [ ] **Step 4: Переписати `landing/README.md`**

Повний новий вміст:
````markdown
# Deai Canvas landing page

The public site at https://neodisa.github.io/deai-canvas/. It is static and uses relative paths.
`.github/workflows/pages.yml` publishes it on every push to `main` that touches `landing/` and after every release.

Local preview from the repository root:

```sh
python3 -m http.server 8080 --bind 127.0.0.1 --directory landing
```

`python3 -B ops/build_site.py --src landing --out <new folder>` builds exactly what Pages serves: these files without this
README, with the newest release tag `vX.Y.Z` written into the footer.

## Editing

The page is designed and reviewed as a Deai Canvas task: comments are pinned on an iteration and an agent makes the next one.
Copy the approved iteration over `landing/` and commit it. Nothing syncs back from the repository to the task.

## Product screenshots

The site uses 2880 px WebP captures in `assets/`; the lightbox opens the same files. Northline (rail booking) and Forma (store
checkout) are fictional. The captures use the actual Deai Canvas UI and locally seeded project data.

To recapture the six screenshots, install the repo's Playwright dependency and Chromium, and have `python3` and `cwebp` on your
path. Then run this from the repository root:

```sh
node ops/landing-shots.mjs
```

The capture script uses a temporary Deai Canvas space and a loopback server. It builds the team preview with the local static
publishing module. The fixtures are in `ops/landing-shots/`.

`node ops/landing-og.mjs` renders the link preview `assets/og.png` (1200×630).

## Demo photography

Only the photographs inside the two fictional projects were generated with an image model. The landing page depicts the rendered
prototypes inside real Deai Canvas captures. The prompts:

**Northline** (`ops/landing-shots/northline-rail.webp`)

> Use case: photorealistic-natural. Asset type: wide photo header inside a fictional European rail booking prototype, Northline. An exceptional editorial travel photograph, panoramic 3:2 frame composed to also crop to a wide 3.5:1 ribbon through the middle: a single small red passenger train winding from left toward center along a Swiss Alpine valley, looking slightly down from the opposite grassy hillside. Folded emerald and olive slopes, pale limestone mountain faces in the distance, a few faraway dark trees, fine film grain, clean natural midmorning light. The train is sharp enough to recognize at small size. Darker uncluttered hillside on the left for separate white website text to be placed later. Authentic medium-format travel editorial, richly colored and tactile, no text, no logos, no graphic design or UI.

**Forma** (`ops/landing-shots/forma-chair.webp`)

> Use case: product-mockup. Asset type: product catalogue photo inside a fictional premium furniture checkout prototype, Forma. A beautiful single caramel brown gently curved upholstered lounge chair on a slender brushed chrome tubular base, in the language of independently designed European modern furniture. Three-quarter angle showing the inviting front and side, centered cleanly on a plain warm grey plaster cyclorama with generous breathing room. Natural sidelight, crisp honest texture, subtle shadow, boutique furniture catalogue editorial, square framing, photographed with great restraint. Chair only, no person, no lettering, no logo, no website UI.

Rethink Sans is distributed under the [SIL Open Font License](assets/rethink-sans-OFL.txt).
````

- [ ] **Step 5: Перегляд — сторінка відкривається, консоль чиста**

Запусти сервер перегляду, відкрий `http://127.0.0.1:8087/`, перевір: усі 6 знімків видно, клік по знімку відкриває лайтбокс,
«Full size ↗» веде на `.webp`, у консолі нема помилок. Зупини сервер за PID.

- [ ] **Step 6: Коміт**

```bash
git add -- landing ops/landing-shots.mjs ops/landing-shots
# тест внутрішніх адрес (див. правила) → OK
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(landing): лендинг у репо — WebP 2880 px без PNG-оригіналів, скрипт знімків" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- landing ops/landing-shots.mjs ops/landing-shots
```

---

### Task 2: Бренд, FAQ, превʼю посилання, версія й Beta у футері

**Files:** Modify: `landing/index.html`, `landing/styles.css`

- [ ] **Step 1: Бренд — «Deai Canvas» скрізь (пін L#4)**

```bash
python3 -B - <<'EOF'
p = 'landing/index.html'
s = open(p, encoding='utf-8').read()
pairs = [
    ('href="#setup">Set up Canvas <span', 'href="#setup">Set up Deai Canvas <span'),
    ('<h3>Open it on the canvas</h3>', '<h3>Open it in Deai Canvas</h3>'),
    ('aria-label="Canvas views"', 'aria-label="Deai Canvas views"'),
    ('alt="Canvas Overview with five', 'alt="Deai Canvas Overview with five'),
    ('is selected in Canvas with', 'is selected in Deai Canvas with'),
    ('Make Canvas fit<br> your workflow.', 'Make Deai Canvas fit<br> your workflow.'),
    ('Enlarge the Canvas modules settings screenshot', 'Enlarge the Deai Canvas modules settings screenshot'),
    ('alongside tasks in Canvas.</dd>', 'alongside tasks in Deai Canvas.</dd>'),
    ('In Canvas, select a live element', 'In Deai Canvas, select a live element'),
    ('without installing Canvas?', 'without installing Deai Canvas?'),
]
for old, new in pairs:
    assert s.count(old) == 1, old
    s = s.replace(old, new)
open(p, 'w', encoding='utf-8').write(s)
EOF
python3 -B -c "import re;print(re.findall(r'(?<!Deai )Canvas', open('landing/index.html').read()))"
```
Очікування: `[]`.

- [ ] **Step 2: FAQ про платформи**

У `landing/index.html` замінити
```html
<p>Python 3.9 or later and Chrome or Edge. Overview snapshots also use Node.js 20+ and Playwright. The bundled launcher is designed for macOS.</p>
```
на
```html
<p>Python 3.9 or later and Chrome or Edge. Overview snapshots also use Node.js 20+ and Playwright. Deai Canvas is made for macOS: the launcher, app icon and autostart. On Windows and Linux, run <code>app/serve.py</code> with Python 3.9+ and open it in Chrome or Edge as an app window. A one-command start on every OS is on the roadmap.</p>
```

- [ ] **Step 3: Превʼю посилання (og/twitter)**

Після рядка `<meta property="og:description" …>` вставити:
```html
  <meta property="og:url" content="https://neodisa.github.io/deai-canvas/">
  <meta property="og:image" content="https://neodisa.github.io/deai-canvas/assets/og.png">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:alt" content="Deai Canvas: a live HTML prototype with pinned feedback on the canvas.">
  <meta name="twitter:card" content="summary_large_image">
  <link rel="canonical" href="https://neodisa.github.io/deai-canvas/">
```
(`assets/og.png` зʼявиться в Task 9.)

- [ ] **Step 4: Версія й Beta у футері (пін L#3)**

У футері між `<a class="brand" …>…</a>` і `<nav aria-label="Footer">` вставити:
```html
      <p class="footer-version"><a href="https://github.com/neodisa/deai-canvas/blob/main/CHANGELOG.md" data-version>v0.39.1</a> · Beta</p>
```
Рівно ОДИН елемент з `data-version` на сторінці (його шукає `ops/build_site.py`).

- [ ] **Step 5: Стилі**

У `landing/styles.css` після правила `.footer-inner { … }` додати:
```css
.footer-version { color: var(--muted); font-size: 13px; font-weight: 600; font-variant-numeric: tabular-nums; }
.footer-version a { color: var(--ink); text-decoration: underline; text-decoration-color: var(--line); text-underline-offset: 3px; }
.footer-version a:hover { text-decoration-color: currentColor; }
.faq details code { font: .9em ui-monospace, SFMono-Regular, Consolas, monospace; }
```

- [ ] **Step 6: Перегляд і коміт**

Перегляд на 1440 px і 375 px: футер не переповнюється (`document.documentElement.scrollWidth === innerWidth`), FAQ відкривається.
```bash
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(landing): бренд Deai Canvas скрізь, FAQ про Windows/Linux, og-превʼю, версія й Beta у футері" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- landing/index.html landing/styles.css
```

---

### Task 3: `ops/release_notes.py` — текст Release з CHANGELOG (TDD)

**Files:**
- Create: `ops/release_notes.py`
- Test: `tests/test_release_notes.py`

- [ ] **Step 1: Тест**

`tests/test_release_notes.py`:
```python
"""`ops/release_notes.py`: секція CHANGELOG для тега `vX.Y.Z` — текст GitHub Release."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'ops'))
import release_notes as rn  # noqa: E402

CL = """# Changelog

Intro.

## [0.40.0] — 01.12.2026

Headline paragraph.

### Додано
- Thing one.

## [0.39.1] — 25.11.2026

Older.
"""
PKG = json.dumps({'name': 'deai-canvas', 'version': '0.40.0'})


class SectionTest(unittest.TestCase):
    def test_takes_only_its_section(self):
        body = rn.section(CL, '0.40.0')
        self.assertTrue(body.startswith('Headline paragraph.'))
        self.assertIn('- Thing one.', body)
        self.assertNotIn('Older.', body)
        self.assertNotIn('## [', body)

    def test_last_section_runs_to_the_end(self):
        self.assertEqual(rn.section(CL, '0.39.1'), 'Older.')

    def test_missing_section(self):
        with self.assertRaises(rn.NotesError):
            rn.section(CL, '0.41.0')

    def test_version_prefix_does_not_match(self):
        with self.assertRaises(rn.NotesError):
            rn.section(CL, '0.39')

    def test_empty_section(self):
        with self.assertRaises(rn.NotesError):
            rn.section('## [1.0.0] — 01.01.2027\n\n## [0.9.0] — 01.12.2026\nx\n', '1.0.0')


class NotesTest(unittest.TestCase):
    def test_section_then_footer(self):
        out = rn.notes('v0.40.0', CL, PKG)
        self.assertTrue(out.startswith('Headline paragraph.'))
        self.assertIn(rn.FOOTER.strip(), out)
        self.assertLess(out.index('- Thing one.'), out.index(rn.FOOTER.strip()))

    def test_tag_must_be_a_release_tag(self):
        for tag in ('0.40.0', 'v0.40', 'v0.40.0-rc1', 'v01.2.3', 'v0.40.0\n', 'release'):
            with self.subTest(tag=tag), self.assertRaises(rn.NotesError):
                rn.notes(tag, CL, PKG)

    def test_package_version_must_match(self):
        with self.assertRaises(rn.NotesError):
            rn.notes('v0.40.0', CL, json.dumps({'version': '0.39.1'}))

    def test_package_must_be_json_object(self):
        for bad in ('nope', '[]'):
            with self.subTest(bad=bad), self.assertRaises(rn.NotesError):
                rn.notes('v0.40.0', CL, bad)


class CliTest(unittest.TestCase):
    def run_cli(self, *args, cwd):
        script = os.path.join(ROOT, 'ops', 'release_notes.py')
        return subprocess.run([sys.executable, '-B', script, *args], cwd=cwd, capture_output=True, text=True)

    def write_repo(self, d):
        with open(os.path.join(d, 'CHANGELOG.md'), 'w', encoding='utf-8') as f:
            f.write(CL)
        with open(os.path.join(d, 'package.json'), 'w', encoding='utf-8') as f:
            f.write(PKG)

    def test_prints_notes(self):
        with tempfile.TemporaryDirectory() as d:
            self.write_repo(d)
            r = self.run_cli('v0.40.0', cwd=d)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('- Thing one.', r.stdout)

    def test_fails_with_a_reason(self):
        with tempfile.TemporaryDirectory() as d:
            self.write_repo(d)
            r = self.run_cli('v9.9.9', cwd=d)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stdout, '')
        self.assertIn('release_notes:', r.stderr)


class RepoTest(unittest.TestCase):
    def test_current_version_has_a_section(self):
        with open(os.path.join(ROOT, 'package.json'), encoding='utf-8') as f:
            version = json.load(f)['version']
        with open(os.path.join(ROOT, 'CHANGELOG.md'), encoding='utf-8') as f:
            self.assertTrue(rn.section(f.read(), version))


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Тест падає**

Run: `python3 -B -m unittest tests.test_release_notes -v`
Expected: `ModuleNotFoundError: No module named 'release_notes'`.

- [ ] **Step 3: Реалізація**

`ops/release_notes.py`:
```python
"""Текст GitHub Release для тега `vX.Y.Z`: секція `## [X.Y.Z]` з CHANGELOG.md і рядок про встановлення.

    python3 -B ops/release_notes.py v0.40.0 [--changelog CHANGELOG.md] [--package package.json]

Друкує текст у stdout. Тег не `vX.Y.Z`, у package.json інша версія, секції нема чи вона порожня — код 1 і причина в stderr:
Release тоді не створюється. Лише stdlib. Викликає `.github/workflows/release.yml`.
"""
import argparse
import json
import re
import sys

#: Той самий тег, що приймає оновлення в застосунку (`app/updater.py`, `TAG_RE`): без пре-релізів і ведучих нулів.
TAG_RE = re.compile(r'^v(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\Z')
#: Заголовок секції — як його читає «What's new» у застосунку (`app/updater.py`, `_CL_HEAD_RE`).
HEAD_RE = re.compile(r'^## \[([0-9][0-9.]*)\] [—–-] [0-9]{2}\.[0-9]{2}\.[0-9]{4}[ \t]*\Z')

FOOTER = (
    '---\n\n'
    'Install: paste the setup prompt into your coding agent, or clone the repository — see '
    '[Get started](https://github.com/neodisa/deai-canvas#get-started). Updates then come from the canvas itself '
    '(Settings → Updates). The "Source code" archives below are not a git checkout and cannot update from the app.\n'
)


class NotesError(Exception):
    """Release для цього тега створювати не можна; текст — причина для людини."""


def section(changelog, version):
    """Тіло секції `## [version] — DD.MM.YYYY` без заголовка, до наступного `## ` або кінця файла."""
    lines = changelog.splitlines()
    start = None
    for i, line in enumerate(lines):
        m = HEAD_RE.match(line)
        if m and m.group(1) == version:
            start = i + 1
            break
    if start is None:
        raise NotesError('CHANGELOG.md has no "## [%s] — DD.MM.YYYY" section' % version)
    end = next((j for j in range(start, len(lines)) if lines[j].startswith('## ')), len(lines))
    body = '\n'.join(lines[start:end]).strip()
    if not body:
        raise NotesError('the "## [%s]" section of CHANGELOG.md is empty' % version)
    return body


def notes(tag, changelog, package_json):
    """Повний текст Release: секція версії тега й FOOTER. Кидає NotesError."""
    if not TAG_RE.match(tag):
        raise NotesError('tag %r is not vX.Y.Z' % tag)
    version = tag[1:]
    try:
        declared = json.loads(package_json).get('version')
    except (ValueError, AttributeError):
        raise NotesError('package.json is not a JSON object') from None
    if declared != version:
        raise NotesError('package.json says %r, the tag says %r' % (declared, version))
    return section(changelog, version) + '\n\n' + FOOTER


def main(argv=None):
    ap = argparse.ArgumentParser(description='GitHub Release notes for a vX.Y.Z tag, taken from CHANGELOG.md.')
    ap.add_argument('tag')
    ap.add_argument('--changelog', default='CHANGELOG.md')
    ap.add_argument('--package', default='package.json')
    args = ap.parse_args(argv)
    try:
        with open(args.changelog, encoding='utf-8') as f:
            changelog = f.read()
        with open(args.package, encoding='utf-8') as f:
            package_json = f.read()
        text = notes(args.tag, changelog, package_json)
    except (NotesError, OSError) as e:
        print('release_notes: %s' % e, file=sys.stderr)
        return 1
    sys.stdout.write(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
```

- [ ] **Step 4: Тести проходять**

Run: `python3 -B -m unittest tests.test_release_notes -v` → усі `ok`.
Run: `python3 -B ops/release_notes.py v0.39.1 | head -5` → перші рядки секції 0.39.1.

- [ ] **Step 5: Коміт**

```bash
git add -- ops/release_notes.py tests/test_release_notes.py
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(release): ops/release_notes.py — текст GitHub Release із секції CHANGELOG" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- ops/release_notes.py tests/test_release_notes.py
```

---

### Task 4: `.github/workflows/release.yml`

**Files:** Create: `.github/workflows/release.yml`

- [ ] **Step 1: Workflow**

```yaml
# GitHub Release для кожного тега vX.Y.Z. Текст — секція CHANGELOG.md (ops/release_notes.py).
# Лише читає тег: не створює й не рухає теги, тож канал оновлень застосунку (git-теги) не зачіпає.
# Workflow береться з ТЕГОВАНОГО коміту: тег, у коміті якого цього файла ще нема, Release не отримає — тоді вручну:
#   python3 -B ops/release_notes.py vX.Y.Z > notes.md && gh release create vX.Y.Z --verify-tag --title "Deai Canvas X.Y.Z" --notes-file notes.md
name: Release

on:
  push:
    tags: ['v*.*.*']

permissions:
  contents: write

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          fetch-depth: 0

      - name: The tagged commit is on main
        run: |
          git fetch --no-tags origin main
          git merge-base --is-ancestor "$GITHUB_SHA" origin/main

      - name: Notes from CHANGELOG.md
        run: python3 -B ops/release_notes.py "$GITHUB_REF_NAME" > "$RUNNER_TEMP/notes.md"

      - name: Create the release
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          if gh release view "$GITHUB_REF_NAME" > /dev/null 2>&1; then
            echo "Release $GITHUB_REF_NAME already exists"
            exit 0
          fi
          gh release create "$GITHUB_REF_NAME" --verify-tag \
            --title "Deai Canvas ${GITHUB_REF_NAME#v}" \
            --notes-file "$RUNNER_TEMP/notes.md"
```

- [ ] **Step 2: YAML читається**

Run: `ruby -ryaml -e 'YAML.load_file(ARGV[0]); puts "ok"' .github/workflows/release.yml` → `ok`.

- [ ] **Step 3: Коміт**

```bash
git add -- .github/workflows/release.yml
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "ci(release): GitHub Release на кожен тег vX.Y.Z з текстом із CHANGELOG" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- .github/workflows/release.yml
```

---

### Task 5: `ops/build_site.py` — `_site/` для Pages (TDD)

**Files:**
- Create: `ops/build_site.py`
- Test: `tests/test_build_site.py`

- [ ] **Step 1: Тест**

`tests/test_build_site.py`:
```python
"""`ops/build_site.py`: копія landing/ для Pages без README.md і з найбільшим тегом vX.Y.Z у [data-version]."""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'ops'))
import build_site as bs  # noqa: E402

HTML = '<footer><p class="footer-version"><a href="x" data-version>v0.39.1</a> · Beta</p></footer>'


class LatestTagTest(unittest.TestCase):
    def test_numeric_order(self):
        self.assertEqual(bs.latest_tag(['v0.9.9', 'v0.10.0', 'v0.2.0']), 'v0.10.0')

    def test_ignores_non_release_tags(self):
        self.assertEqual(bs.latest_tag(['v1.0.0-rc1', 'backup-2026', 'v2', 'v0.3.0', 'v01.0.0']), 'v0.3.0')

    def test_no_tags(self):
        self.assertIsNone(bs.latest_tag([]))


class InjectTest(unittest.TestCase):
    def test_replaces_the_version(self):
        self.assertEqual(bs.inject_version(HTML, 'v0.40.0'), HTML.replace('v0.39.1', 'v0.40.0'))

    def test_needs_exactly_one_marker(self):
        for html in ('<p>no marker</p>', HTML + HTML):
            with self.subTest(html=html), self.assertRaises(ValueError):
                bs.inject_version(html, 'v0.40.0')


class BuildTest(unittest.TestCase):
    def make_src(self, d):
        src = os.path.join(d, 'landing')
        os.makedirs(os.path.join(src, 'assets'))
        for name, text in (('index.html', HTML), ('README.md', 'readme'), ('.DS_Store', 'x'), ('assets/a.webp', 'img')):
            with open(os.path.join(src, name), 'w', encoding='utf-8') as f:
                f.write(text)
        return src

    def test_copies_without_readme_and_writes_the_version(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, '_site')
            bs.build(self.make_src(d), out, 'v0.40.0')
            self.assertEqual(sorted(os.listdir(out)), ['assets', 'index.html'])
            self.assertTrue(os.path.isfile(os.path.join(out, 'assets', 'a.webp')))
            with open(os.path.join(out, 'index.html'), encoding='utf-8') as f:
                self.assertIn('data-version>v0.40.0<', f.read())

    def test_without_a_tag_the_page_is_copied_as_is(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, '_site')
            bs.build(self.make_src(d), out, None)
            with open(os.path.join(out, 'index.html'), encoding='utf-8') as f:
                self.assertEqual(f.read(), HTML)

    def test_refuses_an_existing_out_folder(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, '_site')
            os.makedirs(out)
            with self.assertRaises(FileExistsError):
                bs.build(self.make_src(d), out, 'v0.40.0')
            self.assertEqual(os.listdir(out), [])

    def test_real_landing_has_one_marker(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, '_site')
            bs.build(os.path.join(ROOT, 'landing'), out, 'v9.9.9')
            with open(os.path.join(out, 'index.html'), encoding='utf-8') as f:
                self.assertIn('data-version>v9.9.9<', f.read())


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Тест падає**

Run: `python3 -B -m unittest tests.test_build_site -v` → `ModuleNotFoundError: No module named 'build_site'`.

- [ ] **Step 3: Реалізація**

`ops/build_site.py`:
```python
"""Збирає сайт для GitHub Pages: копія `landing/` без README.md, найбільший тег `vX.Y.Z` — у єдиний елемент `[data-version]`.

    python3 -B ops/build_site.py --src landing --out _site [--tag vX.Y.Z]

Без `--tag` береться найбільший тег `vX.Y.Z` репозиторію (`git tag`); тегів нема — сторінка копіюється як є. Тека `--out` не
повинна існувати (нічого не перезаписуємо). Лише stdlib. Викликає `.github/workflows/pages.yml`.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys

#: Той самий тег, що приймає оновлення в застосунку (`app/updater.py`, `TAG_RE`).
TAG_RE = re.compile(r'^v(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\Z')
#: Елемент, куди пишеться версія: `<a … data-version …>v0.39.1</a>`.
VERSION_RE = re.compile(r'(<([a-z]+)\b[^>]*\bdata-version\b[^>]*>)[^<]*(</\2>)')
SKIP = {'README.md', '.DS_Store'}


def latest_tag(tags):
    """Найбільший за числами тег `vX.Y.Z` зі списку або None."""
    best = None
    for tag in tags:
        tag = tag.strip()
        m = TAG_RE.match(tag)
        if m:
            key = tuple(int(x) for x in m.groups())
            if best is None or key > best[0]:
                best = (key, tag)
    return best[1] if best else None


def git_tags(repo):
    out = subprocess.run(['git', 'tag', '--list', 'v*'], cwd=repo, capture_output=True, text=True, check=True).stdout
    return out.splitlines()


def inject_version(html, tag):
    """Вписати тег в ЄДИНИЙ елемент `[data-version]`; нуль чи кілька таких елементів — ValueError."""
    new, n = VERSION_RE.subn(lambda m: m.group(1) + tag + m.group(3), html)
    if n != 1:
        raise ValueError('expected exactly one [data-version] element, found %d' % n)
    return new


def build(src, out, tag):
    if os.path.exists(out):
        raise FileExistsError(out)
    shutil.copytree(src, out, ignore=lambda _dir, names: [n for n in names if n in SKIP])
    if tag:
        page = os.path.join(out, 'index.html')
        with open(page, encoding='utf-8') as f:
            html = f.read()
        with open(page, 'w', encoding='utf-8') as f:
            f.write(inject_version(html, tag))


def main(argv=None):
    ap = argparse.ArgumentParser(description='Build the GitHub Pages site from landing/.')
    ap.add_argument('--src', default='landing')
    ap.add_argument('--out', required=True)
    ap.add_argument('--tag', help='vX.Y.Z; default: the newest vX.Y.Z tag of the repository')
    args = ap.parse_args(argv)
    if args.tag is not None and not TAG_RE.match(args.tag):
        print('build_site: --tag must be vX.Y.Z', file=sys.stderr)
        return 2
    tag = args.tag or latest_tag(git_tags(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    try:
        build(args.src, args.out, tag)
    except (OSError, ValueError) as e:
        print('build_site: %s' % e, file=sys.stderr)
        return 1
    print('built %s (%s)' % (args.out, tag or 'no release tag'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
```

- [ ] **Step 4: Тести проходять + реальна збірка**

Run: `python3 -B -m unittest tests.test_build_site -v` → усі `ok`.
Run (тека в scratch, не в репо):
```bash
OUT="$(mktemp -d)/_site"; python3 -B ops/build_site.py --src landing --out "$OUT" && grep -o 'data-version>[^<]*' "$OUT/index.html" && ls "$OUT"
```
Очікування: `built … (v0.39.1)` (або новіший тег), `data-version>v0.39.1`, у переліку нема `README.md`.

- [ ] **Step 5: Коміт**

```bash
git add -- ops/build_site.py tests/test_build_site.py
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(pages): ops/build_site.py — сайт із landing/ з версією останнього релізу" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- ops/build_site.py tests/test_build_site.py
```

---

### Task 6: `.github/workflows/pages.yml`

**Files:** Create: `.github/workflows/pages.yml`

- [ ] **Step 1: Workflow**

```yaml
# Публікує landing/ на GitHub Pages (https://neodisa.github.io/deai-canvas/).
# workflow_run після «Release», а не push тегів: середовище github-pages типово пускає деплой лише з main,
# а workflow_run іде в контексті main — так версія у футері оновлюється з кожним релізом.
# Разове налаштування репозиторію: Settings → Pages → Source: GitHub Actions.
name: Pages

on:
  push:
    branches: [main]
    paths:
      - 'landing/**'
      - 'ops/build_site.py'
      - '.github/workflows/pages.yml'
  workflow_run:
    workflows: [Release]
    types: [completed]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: false

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          ref: main
          fetch-depth: 0
      - uses: actions/configure-pages@v6
      - name: Build the site
        run: python3 -B ops/build_site.py --src landing --out _site
      - uses: actions/upload-pages-artifact@v5
        with:
          path: _site

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v5
```

- [ ] **Step 2: YAML читається**

Run: `ruby -ryaml -e 'YAML.load_file(ARGV[0]); puts "ok"' .github/workflows/pages.yml` → `ok`.

- [ ] **Step 3: Коміт**

```bash
git add -- .github/workflows/pages.yml
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "ci(pages): публікація landing/ на GitHub Pages з версією останнього релізу" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- .github/workflows/pages.yml
```

---

### Task 7: Шапка — Beta, Share, мобільне меню (піни L#3, L#7)

**Files:** Modify: `landing/index.html`, `landing/styles.css`, `landing/site.js`

- [ ] **Step 1: Розмітка шапки**

У `landing/index.html` замінити весь `<div class="wrap masthead">…</div>` (від `<div class="wrap masthead">` до його `</div>`
перед `</header>`) на:
```html
    <div class="wrap masthead">
      <a class="brand" href="#top">
        <img src="assets/deai-icon.png" alt="" width="32" height="32">
        <span>Deai Canvas</span>
        <span class="beta-badge">Beta</span>
      </a>
      <nav class="nav" id="site-nav" aria-label="Main">
        <a href="#workflow">Workflow</a>
        <a href="#modules">Modules</a>
        <a href="#faq">FAQ</a>
        <a href="https://github.com/neodisa/deai-canvas">GitHub <span aria-hidden="true">↗</span></a>
        <a class="nav-setup" href="#setup">Get started <span aria-hidden="true">→</span></a>
      </nav>
      <div class="masthead-actions">
        <button type="button" class="button button-small button-outline share-button" data-share hidden>Share</button>
        <a href="#setup" class="button button-small button-outline header-setup">Get started <span aria-hidden="true">→</span></a>
        <button type="button" class="menu-button" aria-controls="site-nav" aria-expanded="false" data-menu hidden>
          <span class="visually-hidden">Menu</span><span class="menu-icon" aria-hidden="true"></span>
        </button>
      </div>
      <p class="visually-hidden" role="status" data-share-status></p>
    </div>
```

- [ ] **Step 2: Стилі**

У `landing/styles.css`:
1. Замінити `.masthead > .button { justify-self: end; }` на:
```css
.masthead { position: relative; }
.masthead-actions { justify-self: end; display: flex; align-items: center; gap: 8px; }
.beta-badge { padding: 2px 6px 3px; border-radius: 5px; background: var(--lime); color: #2c4a31; font-size: 11px; font-weight: 720; line-height: 1.3; letter-spacing: .03em; text-transform: uppercase; }
.nav-setup, .menu-button { display: none; }
@media (min-width: 761px) { .share-button { min-width: 108px; } }
```
2. Усередину `@media (max-width: 760px) { … }` додати:
```css
  .masthead { grid-template-columns: 1fr auto; }
  .nav { display: none; }
  .menu-button { display: inline-grid; place-items: center; width: 44px; height: 42px; padding: 0; border: 1px solid #aebbb0; border-radius: 8px; background: transparent; }
  .menu-button:hover { background: #e8ede4; border-color: #7b8d80; }
  .menu-icon, .menu-icon::before { display: block; width: 16px; height: 1.5px; border-radius: 1px; background: currentColor; transition: translate 170ms var(--ease), rotate 170ms var(--ease); }
  .menu-icon { position: relative; translate: 0 -3px; }
  .menu-icon::before { content: ""; position: absolute; translate: 0 6px; }
  .menu-button[aria-expanded="true"] .menu-icon { translate: 0; rotate: 45deg; }
  .menu-button[aria-expanded="true"] .menu-icon::before { translate: 0; rotate: -90deg; }
  .nav.is-open { position: absolute; z-index: 3; inset: calc(100% + 1px) calc(var(--gutter) * -1) auto; display: grid; gap: 0; padding: 4px var(--gutter) 12px; background: var(--paper); border-bottom: 1px solid var(--line); box-shadow: 0 18px 28px -22px #1a332c66; }
  .nav.is-open a { min-height: 50px; border-bottom: 1px solid var(--line); color: var(--ink); font-size: 16px; }
  .nav.is-open a:last-child { border-bottom: 0; }
```
3. Усередину `@media (max-width: 560px) { … }` додати:
```css
  .header-setup { display: none; }
  .nav.is-open .nav-setup { display: inline-flex; }
```

- [ ] **Step 3: JS — копіювання тексту, Share, меню**

У `landing/site.js` наприкінці файла додати:
```js
async function copyText(text) {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Fall back to a hidden textarea when the browser denies clipboard access.
    }
  }
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.append(area);
  area.select();
  const copied = document.execCommand("copy");
  area.remove();
  return copied;
}

const SHARE = {
  title: "Deai Canvas",
  text: "Deai Canvas — a local workspace for reviewing what your AI agent designs. Check it out:",
  url: "https://neodisa.github.io/deai-canvas/",
};
const shareButton = document.querySelector("[data-share]");
const shareStatus = document.querySelector("[data-share-status]");
let shareTimer;

shareButton.hidden = false;
shareButton.addEventListener("click", async () => {
  if (navigator.share && matchMedia("(pointer: coarse)").matches) {
    try {
      await navigator.share(SHARE);
    } catch {
      // The share sheet was closed.
    }
    return;
  }
  clearTimeout(shareTimer);
  const copied = await copyText(`${SHARE.text} ${SHARE.url}`);
  shareButton.textContent = copied ? "Link copied" : "Copy failed";
  shareStatus.textContent = copied ? "A link to Deai Canvas was copied to the clipboard." : "The link could not be copied.";
  shareTimer = setTimeout(() => { shareButton.textContent = "Share"; }, 2400);
});

const menuButton = document.querySelector("[data-menu]");
const siteNav = document.getElementById("site-nav");
const compactHeader = matchMedia("(max-width: 760px)");

function setMenu(open, focusButton = false) {
  menuButton.setAttribute("aria-expanded", String(open));
  siteNav.classList.toggle("is-open", open);
  if (!open && focusButton) menuButton.focus();
}

menuButton.hidden = false;
menuButton.addEventListener("click", () => setMenu(menuButton.getAttribute("aria-expanded") !== "true"));
siteNav.addEventListener("click", (event) => {
  if (event.target.closest("a")) setMenu(false);
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && siteNav.classList.contains("is-open")) setMenu(false, true);
});
document.addEventListener("click", (event) => {
  if (siteNav.classList.contains("is-open") && !siteNav.contains(event.target) && !menuButton.contains(event.target)) setMenu(false);
});
compactHeader.addEventListener("change", () => setMenu(false));
```

- [ ] **Step 4: Перегляд**

На 1440, 900, 760, 375 px:
- нема горизонтального скролу (`document.documentElement.scrollWidth === innerWidth`);
- ≥761: навігація в рядок, Share і Get started праворуч; клік Share → «Link copied» на 2,4 с, у буфері текст із посиланням;
- ≤760: навігації нема, є кнопка меню; клік відкриває список, Esc закриває й повертає фокус на кнопку, клік повз — закриває;
- ≤560: «Get started» лише в меню; `Beta` поруч із назвою не переноситься;
- консоль чиста.

- [ ] **Step 5: Коміт**

```bash
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(landing): шапка — плашка Beta, кнопка Share, мобільне меню" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- landing/index.html landing/styles.css landing/site.js
```

---

### Task 8: «Get started» — агент / Термінал і «Connect your agent»

**Files:** Modify: `landing/index.html`, `landing/styles.css`, `landing/site.js`

- [ ] **Step 1: Розмітка**

У `landing/index.html` замінити всю `<section class="setup wrap" id="setup" …>…</section>` на:
```html
    <section class="setup wrap" id="setup" aria-labelledby="setup-title">
      <div class="setup-board">
        <div class="setup-copy">
          <h2 id="setup-title">Start with<br> your agent.</h2>
          <p>Paste the setup prompt into Claude Code, Codex, or another coding agent that can work with local files. No agent? Run one command in Terminal.</p>
          <h3 class="connect-title">Connect your agent</h3>
          <ol class="connect-steps">
            <li><span><strong>Install.</strong> The agent clones Deai Canvas, starts it and sets up your first space.</span></li>
            <li><span><strong>It learns the space.</strong> Each space folder has an <code>AGENTS.md</code> with the routes and reference topics the agent reads. For Claude Code, connect it once in Settings → AGENTS.md, and its edits show as AI in the history.</span></li>
            <li><span><strong>Work in a loop.</strong> Pin a comment on an element. The agent reads the pins, makes a new iteration and closes each pin with a note.</span></li>
          </ol>
        </div>
        <div class="setup-action">
          <div class="setup-tabs" data-setup-tabs role="tablist" aria-label="Ways to install Deai Canvas" hidden>
            <button type="button" class="setup-tab" role="tab" id="setup-tab-agent" aria-controls="setup-agent" aria-selected="true">With your agent</button>
            <button type="button" class="setup-tab" role="tab" id="setup-tab-terminal" aria-controls="setup-terminal" aria-selected="false" tabindex="-1">In Terminal <span class="setup-tab-note">macOS</span></button>
          </div>
          <div class="prompt-card" id="setup-agent">
            <div class="prompt-toolbar"><span><span aria-hidden="true">&gt;_</span> Setup prompt</span><button class="button button-small copy-button" type="button" data-copy="setup-prompt" hidden>Copy prompt</button></div>
            <p><code id="setup-prompt">Install Deai Canvas: clone https://github.com/neodisa/deai-canvas.git into ~/deai-canvas and follow ~/deai-canvas/SETUP.md.</code></p>
          </div>
          <div class="prompt-card" id="setup-terminal">
            <div class="prompt-toolbar"><span><span aria-hidden="true">$</span> Terminal · macOS</span><button class="button button-small copy-button" type="button" data-copy="setup-command" hidden>Copy command</button></div>
            <p><code id="setup-command">git clone https://github.com/neodisa/deai-canvas.git ~/deai-canvas &amp;&amp; cd ~/deai-canvas &amp;&amp; bash ops/canvas-app/install.sh &amp;&amp; ./start.command</code></p>
            <p class="prompt-note">For Overview snapshots, also run <code>npm ci &amp;&amp; npx playwright install chromium</code> in the same folder (Node.js 20+).</p>
          </div>
          <p class="copy-status visually-hidden" role="status" data-copy-status></p>
          <a class="text-link manual-link" href="https://github.com/neodisa/deai-canvas/blob/main/SETUP.md">Read the installation guide <span aria-hidden="true">↗</span></a>
        </div>
      </div>
    </section>
```

- [ ] **Step 2: Стилі**

У `landing/styles.css` після `.manual-link { margin-top: 6px; }` додати:
```css
.setup-tabs { display: flex; gap: 4px; width: fit-content; margin-bottom: 10px; padding: 4px; border-radius: 10px; background: #cfe3a4; }
.setup-tab { min-height: 40px; padding: 0 14px; border: 0; border-radius: 7px; background: transparent; color: #314b37; font-size: 14px; font-weight: 640; transition: background-color 170ms var(--ease), color 170ms var(--ease); }
.setup-tab:hover { color: var(--ink); }
.setup-tab[aria-selected="true"] { background: var(--pine); color: var(--on-pine); }
.setup-tab-note { margin-left: 3px; font-size: 12px; opacity: .72; }
.setup-action .prompt-card + .prompt-card { margin-top: 10px; }
.prompt-card .prompt-note { padding: 0 16px 16px; color: var(--pine-muted); font-size: 13px; }
.prompt-note code { font: 12px/1.6 ui-monospace, SFMono-Regular, Consolas, monospace; color: #e3ecdd; overflow-wrap: anywhere; }
.connect-title { margin-top: 26px; font-size: 17px; font-weight: 700; letter-spacing: -.014em; }
.connect-steps { display: grid; gap: 9px; max-width: 46ch; margin: 8px 0 0; padding: 0; list-style: none; counter-reset: step; }
.connect-steps li { counter-increment: step; display: grid; grid-template-columns: 22px minmax(0, 1fr); gap: 6px; color: #314b37; font-size: 15px; }
.connect-steps li::before { content: counter(step); color: #537559; font-weight: 700; font-variant-numeric: tabular-nums; }
.connect-steps strong { color: var(--ink); }
.connect-steps code { font: .9em ui-monospace, SFMono-Regular, Consolas, monospace; }
```

- [ ] **Step 3: JS — спільні вкладки й копіювання**

У `landing/site.js`:
1. Замінити блок від `const tabList = document.querySelector("[data-gallery-tabs]");` до кінця обробника `keydown`
   (рядки 1–47 вихідного файла) на:
```js
function initTabs(tabList, horizontalQuery) {
  const tabs = [...tabList.querySelectorAll('[role="tab"]')];
  const panels = tabs.map((tab) => document.getElementById(tab.getAttribute("aria-controls")));
  const horizontal = () => !horizontalQuery || horizontalQuery.matches;

  function show(index) {
    tabs.forEach((tab, i) => {
      const selected = i === index;
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
      panels[i].hidden = !selected;
    });
  }

  function setOrientation() {
    tabList.setAttribute("aria-orientation", horizontal() ? "horizontal" : "vertical");
  }

  tabs.forEach((tab, i) => {
    panels[i].setAttribute("role", "tabpanel");
    panels[i].setAttribute("aria-labelledby", tab.id);
    tab.addEventListener("click", () => show(i));
  });
  setOrientation();
  horizontalQuery?.addEventListener("change", setOrientation);
  show(0);
  tabList.hidden = false;

  tabList.addEventListener("keydown", (event) => {
    const current = tabs.indexOf(event.target);
    if (current < 0 || event.altKey || event.ctrlKey || event.metaKey) return;
    const previous = horizontal() ? "ArrowLeft" : "ArrowUp";
    const next = horizontal() ? "ArrowRight" : "ArrowDown";
    const last = tabs.length - 1;
    let index;
    switch (event.key) {
      case previous: index = current === 0 ? last : current - 1; break;
      case next: index = current === last ? 0 : current + 1; break;
      case "Home": index = 0; break;
      case "End": index = last; break;
      default: return;
    }
    event.preventDefault();
    show(index);
    tabs[index].focus();
  });
}

initTabs(document.querySelector("[data-gallery-tabs]"), matchMedia("(max-width: 760px)"));
initTabs(document.querySelector("[data-setup-tabs]"), null);
```
2. Замінити блок від `const copyButton = document.querySelector("[data-copy]");` до кінця його обробника `click`
   (вихідні рядки 80–118) на:
```js
const copyStatus = document.querySelector("[data-copy-status]");

for (const button of document.querySelectorAll("[data-copy]")) {
  const source = document.getElementById(button.dataset.copy);
  const label = button.textContent;
  let timer;
  button.hidden = false;
  button.addEventListener("click", async () => {
    clearTimeout(timer);
    if (await copyText(source.textContent.trim())) {
      button.textContent = "Copied";
      copyStatus.classList.add("visually-hidden");
      copyStatus.textContent = "Copied to clipboard.";
      timer = setTimeout(() => { button.textContent = label; }, 2400);
    } else {
      const selection = getSelection();
      const range = document.createRange();
      range.selectNodeContents(source);
      selection.removeAllRanges();
      selection.addRange(range);
      button.textContent = label;
      copyStatus.classList.remove("visually-hidden");
      copyStatus.textContent = "Text selected. Press Ctrl+C or ⌘C to copy.";
    }
  });
}
```
`copyText` визначена в Task 7 нижче у файлі: це `async function` (піднімається), тож порядок у файлі не важливий.

- [ ] **Step 4: Перегляд**

- З JS: дві вкладки, видно лише картку вибраної; ←/→ перемикають; «Copy prompt» і «Copy command» кладуть у буфер саме свій текст
  (`&&` без `&amp;`); галерея працює як раніше (↑/↓ на десктопі, ←/→ на ≤760).
- Без JS (DevTools → Disable JavaScript): обидві картки одна під одною, вкладок нема.
- 375 px: команда переноситься, нема горизонтального скролу; нумерований список «Connect your agent» рівний.

- [ ] **Step 5: Коміт**

```bash
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(landing): Get started — вкладки «агент / Термінал» і «Connect your agent»" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- landing/index.html landing/styles.css landing/site.js
```

---

### Task 9: `og.png` — картинка превʼю посилання

**Files:** Create: `ops/landing-og.mjs`, `landing/assets/og.png`

- [ ] **Step 1: Скрипт**

`ops/landing-og.mjs`:
```js
// Renders landing/assets/og.png (1200×630), the link preview of the landing page.
// Run from the repository root: node ops/landing-og.mjs (needs the repo's Playwright and its Chromium).
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const asset = (name, type) => `data:${type};base64,${readFileSync(path.join(root, "landing/assets", name)).toString("base64")}`;

const html = `<!doctype html><html><head><meta charset="utf-8"><style>
@font-face { font-family: "Rethink Sans"; src: url(${asset("rethink-sans.woff2", "font/woff2")}) format("woff2"); font-weight: 400 800; }
* { box-sizing: border-box; margin: 0; }
body { position: relative; width: 1200px; height: 630px; overflow: hidden; background: #f5f6f1; color: #182820;
  font-family: "Rethink Sans", sans-serif; -webkit-font-smoothing: antialiased; }
.brand { position: absolute; left: 64px; top: 58px; display: flex; align-items: center; gap: 12px; font-size: 28px; font-weight: 740; letter-spacing: -.04em; }
.brand img { width: 44px; height: 44px; }
.badge { padding: 3px 8px 4px; border-radius: 6px; background: #def1b7; color: #2c4a31; font-size: 14px; font-weight: 720; letter-spacing: .03em; text-transform: uppercase; }
h1 { position: absolute; left: 64px; top: 178px; font-size: 64px; font-weight: 650; line-height: .98; letter-spacing: -.04em; }
p { position: absolute; left: 64px; top: 330px; width: 440px; color: #4d5c52; font-size: 23px; line-height: 1.38; }
.stage { position: absolute; left: 600px; top: 96px; width: 660px; height: 600px; padding: 34px; border-radius: 18px;
  background-color: #def1b7; background-image: radial-gradient(circle, #547b4d52 .9px, transparent 1.2px), linear-gradient(150deg, #eaf6d3, #d9edaf 60%, #cce4b5);
  background-size: 18px 18px, auto; }
.stage img { width: 760px; border-radius: 12px; box-shadow: 0 3px 8px #192a1a26, 0 24px 45px -22px #283f256b; }
</style></head><body>
<div class="brand"><img src="${asset("deai-icon.png", "image/png")}" alt=""><span>Deai Canvas</span><span class="badge">Beta</span></div>
<h1>Design with AI.<br>Keep control.</h1>
<p>A local workspace for reviewing what your AI agent designs: live screens, pinned feedback, iterations.</p>
<div class="stage"><img src="${asset("northline-review.webp", "image/webp")}" alt=""></div>
</body></html>`;

const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1 });
  await page.setContent(html, { waitUntil: "load" });
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: path.join(root, "landing/assets/og.png") });
  console.log("landing/assets/og.png");
} finally {
  await browser.close();
}
```

- [ ] **Step 2: Рендер і перевірка**

Run: `node ops/landing-og.mjs` → `landing/assets/og.png`.
Run: `sips -g pixelWidth -g pixelHeight landing/assets/og.png` → `1200` × `630`; розмір файла < 600 КБ (`ls -l`).
Відкрий картинку (Read): текст не налазить на «сцену», шрифт — Rethink Sans (не системний), знімок видно. Якщо налазить —
зменш `h1` до 60px або посунь `.stage` праворуч (`left: 620px`) і перерендер.

- [ ] **Step 3: Коміт**

```bash
git add -- ops/landing-og.mjs landing/assets/og.png
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(landing): og.png 1200×630 і скрипт його рендеру" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- ops/landing-og.mjs landing/assets/og.png
```

---

### Task 10: README — «Get started», «Connect your agent», посилання на сайт

**Files:** Modify: `README.md` (лише верх, до `## Why`)

- [ ] **Step 1: Знайти посилання на старий якір**

Run: `grep -rn "#install\b" --include=*.md . | grep -v node_modules` — кожне посилання на `README.md#install` перевести на
`#get-started` у цьому ж коміті (лише в `README.md`, `SETUP.md`, `docs/`; `CHANGELOG.md` НЕ чіпати).

- [ ] **Step 2: Нова шапка README**

Замінити в `README.md` усе від рядка `**A local workspace for reviewing the HTML mockups an AI agent writes.**` до рядка перед
`## Why` (не включно) на:
````markdown
**A local workspace for reviewing the HTML mockups an AI agent writes.** The agent (Claude Code or any
other) makes the pages. Deai Canvas keeps every iteration, shows all screens at once, lets you point at an
element and tell the agent what to change, and publishes a protected preview for your team.

[Website](https://neodisa.github.io/deai-canvas/) · [What's new](CHANGELOG.md) · [Setup guide for agents](SETUP.md)

![Deai Canvas: the workplace with the page tree, a mockup, pinned comments and the agent status](docs/screenshots/hero.png)

## Get started

**With your agent.** Paste this into Claude Code, Codex or another agent that can work with files and a terminal. It installs
what is missing, starts the canvas, creates your first space and modules, and asks only for the space name, where to publish
and the preview password:

```text
Install Deai Canvas: clone https://github.com/neodisa/deai-canvas.git into ~/deai-canvas and follow ~/deai-canvas/SETUP.md.
```

Українською:

```text
Встанови Deai Canvas: склонуй https://github.com/neodisa/deai-canvas.git у ~/deai-canvas і зроби все за ~/deai-canvas/SETUP.md.
```

**In Terminal (macOS).**

```bash
git clone https://github.com/neodisa/deai-canvas.git ~/deai-canvas && cd ~/deai-canvas
bash ops/canvas-app/install.sh                   # app icon and autostart
./start.command                                  # then open http://localhost:8765/app/
npm ci && npx playwright install chromium        # optional: Overview snapshots, needs Node.js 20+
```

On Windows and Linux, run `app/serve.py` with Python 3.9+ and open http://localhost:8765/app/ in Chrome or Edge.
Updates come from the canvas itself (Settings → Updates), so keep the folder a git checkout: a downloaded zip cannot update.

The canvas opens on a welcome screen: copy the prompt from there to an agent, or create a space with the wizard.
⌘K → "Canvas tour" shows the map of the workplace and a demo task.

## Connect your agent

Deai Canvas works with any coding agent that can read and write files on your computer: Claude Code, Codex and others.

1. **Install** with the prompt above, or point the agent at an existing space folder.
2. **The space tells the agent how to work.** Every space folder has an `AGENTS.md` with the canvas routes and the reference
   topics the agent reads on its own. For Claude Code the folder also gets a `CLAUDE.md` with `@AGENTS.md`; in
   Settings → AGENTS.md, «Підключити» in the «Claude Code» row adds a Stop hook, so Claude's edits are saved as AI edits in the
   iteration history. Start Claude Code in the space folder, not inside a task folder.
3. **Work in a loop.** Pin a comment on an element. The agent reads the pins, makes a new iteration and closes each pin with a
   note about what it changed.

See *AGENTS.md* below for what the file holds and how the canvas keeps it current.
````

- [ ] **Step 3: Перевірка**

Run: `grep -n "^## " README.md | head -5` → `## Get started`, `## Connect your agent`, `## Why`, …
Run: `grep -n "^### AGENTS.md" README.md` → є (на нього посилається останній рядок нового розділу).

- [ ] **Step 4: Коміт (окремий: README — лише README і якорі)**

```bash
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "docs(readme): Get started (агент / Термінал), Connect your agent, посилання на сайт" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- README.md
```
(Якщо Step 1 змінив інші файли — додай їх шляхи в той самий коміт.)

---

### Task 11: Контрольна точка з власником (візуальне)

Виконує контролер, не субагент.

- [ ] **Step 1:** Підняти перегляд `landing/` worktree на 127.0.0.1:8087, показати власнику десктоп і 375 px: шапку (Beta, Share,
  меню), «Get started» (вкладки, Connect your agent), футер (версія), FAQ, `og.png`.
- [ ] **Step 2:** Правки власника — окремими комітами в `landing/`.
- [ ] **Step 3:** З разового «так» власника — покласти `landing/` ітерацією 2 у задачу канваса «Deai Canvas · лендинг» за
  маршрутом з `AGENTS.md` простору Personal; відповісти на піни L#3, L#4, L#7 і закрити їх із приміткою.

---

### Task 12: Фінальна перевірка й передача

- [ ] **Step 1: Тести**

```bash
python3 -B -m unittest tests.test_release_notes tests.test_build_site -v
DEAI_FORBIDDEN_LIST="$HOME/Liga Tools/design-office-transition/scripts/deai-forbidden.txt" DEAI_REQUIRE_FORBIDDEN_LIST=1 python3 -B -m unittest tests.test_no_internal_addresses
```
Очікування: усе `OK`.

- [ ] **Step 2: Межі змін**

Run: `git diff --stat origin/main...HEAD` — лише `landing/`, `ops/landing-*`, `ops/landing-shots/`, `ops/release_notes.py`,
`ops/build_site.py`, `tests/test_release_notes.py`, `tests/test_build_site.py`, `.github/workflows/`, `README.md`,
`docs/superpowers/`. Нема `app/`, `CHANGELOG.md`, `package.json`.

- [ ] **Step 3: Лендинг — останній прохід**

1440 / 768 / 375 px: нема горизонтального скролу, консоль чиста, вкладки й меню з клавіатури, `prefers-reduced-motion` не ламає
сторінку, `python3 -B ops/build_site.py --src landing --out <scratch>/_site` дає версію у футері.

- [ ] **Step 4: Передача власнику — кожна дія з його окремим «так»**

1. Пуш гілки (перед пушем: `git remote get-url origin` = `https://github.com/neodisa/deai-canvas`, SHA гілки = `HEAD`).
2. Злиття в `main` — рішення власника (PR або його злиття).
3. Settings → Pages → Source: GitHub Actions (власник або `gh api` після «так»).
4. Повідомити сесію релізу 0.40: `release.yml` має бути в `main` до релізного коміту 0.40, інакше перший Release — вручну
   (команда в коментарі `release.yml`).
