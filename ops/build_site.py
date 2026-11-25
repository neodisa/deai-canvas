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
VERSION_RE = re.compile(r'(<([a-z]+)\b[^>]*(?<![\w-])data-version(?![\w-])[^>]*>)[^<]*(</\2>)')
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
    try:
        tag = args.tag or latest_tag(git_tags(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        build(args.src, args.out, tag)
    except (OSError, ValueError, subprocess.CalledProcessError) as e:
        print('build_site: %s' % e, file=sys.stderr)
        return 1
    print('built %s (%s)' % (args.out, tag or 'no release tag'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
