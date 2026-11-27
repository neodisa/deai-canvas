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
    except (NotesError, OSError, ValueError) as e:
        print('release_notes: %s' % e, file=sys.stderr)
        return 1
    sys.stdout.write(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
