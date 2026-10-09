#!/usr/bin/env python3
"""Імпорт ітерації з ЧУЖОГО опублікованого превʼю в задачу — для Claude (fb-29092026-210ec1).

  import_preview.py --task-dir D <url превʼю> [--it itN] [--dry-run]

Колега публікує ту саму задачу у свій Vercel-проєкт — і його ітерації живуть лише
там. Раніше їх переносили руками: зняти сніпет коментатора й гейт, відновити
title з `__origTitle`. Ця команда:
  1. читає `<url>/manifest.json` (джерело правди оболонки превʼю): ітерації,
     сторінки, дерево `outline`; без `--it` бере ОСТАННЮ;
  2. збирає файли за посиланнями зі сторінок, CSS і JS — статичний хостинг
     переліку файлів не віддає, тож інакше спільні assets/icons/fonts і ліниві
     чанки SPA не знайти; чого не знайшлось — каже переліком, а не мовчить;
  3. вирізає зі сторінок вставки публікації (сніпет коментатора, гейт,
     нейтральний title) — рівно ті, що вставляє `serve._publish`;
  4. кладе ітерацію новою `itN` як ЧУЖУ (джерело — превʼю) і поруч МОЮ робочу
     копію: робота не починається поверх чужої ітерації (рішення 15.09.2026,
     так само робить pull з GitLab).

⛔ У git НЕ комітить і нічого не пушить (як `pages.py`): коміт зробить канвас на
наступній дії над задачею. Імпорт не сміє сам відправляти чуже в GitLab.
Прихованих у превʼю сторінок там немає — і після імпорту їх теж не буде.
"""
import argparse
import json
import os
import posixpath
import re
import socket
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import unquote, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'app'))
import pages_model as pm  # noqa: E402
import serve  # noqa: E402


class FetchError(Exception):
    def __init__(self, msg, code=None):
        super().__init__(msg)
        self.code = code


class ImportError_(Exception):  # noqa: N801 — не плутати з вбудованим ImportError
    pass


# Межі вставок публікації — ПЕРШІ й ОСТАННІ символи тих самих шаблонів, що
# вставляє `serve._publish`. Беремо їх із шаблонів, а не переписуємо тут: шаблон
# поміняється — межа поміняється разом із ним (коловий тест стереже).
_SNIPPET_HEAD = serve.COMMENT_SNIPPET.lstrip('\n').split('\n', 2)
_SNIPPET_START = '\n' + _SNIPPET_HEAD[0] + '\n' + _SNIPPET_HEAD[1]
_NEUTRAL_TITLE = '<title>Перегляд макета</title>'
_ORIG_RE = re.compile(r'<script>window\.__origTitle=(".*?");</script>', re.S)


def _gate_end():
    """Хвіст гейта — останні символи шаблону після форматування (параметри
    шаблону стоять раніше, хвіст від них не залежить)."""
    tail = serve.GATE_SNIPPET.rstrip()
    return tail[-60:].replace('{{', '{').replace('}}', '}')


def strip_publish(html):
    """Вирізати вставки публікації. → (чиста сторінка, чи були вставки).

    Порядок у `_publish`: перед `</body>` спершу сніпет коментатора, потім
    `<script>window.__origTitle=…</script>` і гейт; title замінено нейтральним.
    Вирізаємо від початку сніпета до кінця гейта — між ними лише наше."""
    start = html.find(_SNIPPET_START)
    end_mark = _gate_end()
    end = html.find(end_mark, start if start >= 0 else 0)
    if start < 0 or end < 0:
        return html, False
    m = _ORIG_RE.search(html, start, end + len(end_mark))
    out = html[:start] + html[end + len(end_mark):]
    if m and _NEUTRAL_TITLE in out:
        out = out.replace(_NEUTRAL_TITLE, f'<title>{json.loads(m.group(1))}</title>', 1)
    return out, True


def outline_tree(outline, it):
    """Пласкі рядки `manifest.outline` однієї ітерації → дерево pages.json."""
    tree, stack = [], []
    for row in outline:
        if row.get('it') != it:
            continue
        node = {'id': row['key'], 'name': row.get('name') or row['key'], 'kind': row.get('kind') or 'page'}
        depth = int(row.get('depth') or 0)
        del stack[depth:]
        if stack:
            stack[-1].setdefault('children', []).append(node)
        else:
            tree.append(node)
        stack.append(node)
    return tree


_ASSET = r'[\w\-./@%]+\.(?:js|mjs|css|svg|png|jpe?g|gif|webp|avif|ico|woff2?|ttf|otf|eot|json|mp4|webm)'
_HTML_ATTR = re.compile(r'\b(?:src|href|poster|data-src)\s*=\s*["\']([^"\']+)["\']', re.I)
_SRCSET = re.compile(r'\bsrcset\s*=\s*["\']([^"\']+)["\']', re.I)
_CSS_URL = re.compile(r'url\(\s*["\']?([^"\')]+)["\']?\s*\)', re.I)
_CSS_IMPORT = re.compile(r'@import\s+["\']([^"\']+)["\']', re.I)
_JS_STR = re.compile(r'["\'`](' + _ASSET + r')["\'`]', re.I)


def _keep(u):
    """Відносне посилання на файл ітерації, або None. ⛔ Шлях від КОРЕНЯ сайту
    (`/…`) до теки ітерації не належить: у превʼю ітерація лежить у `<it>/`, а
    такі посилання — дані застосунку (на boss-interface it15 — 252 картинки, яких
    немає і в самому превʼю). `%23…` — закодований якір."""
    u = unquote(u.strip())
    if not u or u.startswith(('#', '/', 'data:', 'mailto:', 'tel:', 'javascript:')):
        return None
    if urlparse(u).scheme:
        return None
    return u.split('#', 1)[0].split('?', 1)[0] or None


def refs(text, kind):
    """Відносні посилання з HTML/CSS/JS. Зовнішні, data:, якорі — ні."""
    found = []
    if kind == 'html':
        found += _HTML_ATTR.findall(text)
        for ss in _SRCSET.findall(text):
            found += [part.strip().split()[0] for part in ss.split(',') if part.strip()]
        for style in re.findall(r'<style[^>]*>(.*?)</style>', text, re.S | re.I):
            found += list(refs(style, 'css'))
    elif kind == 'css':
        found += _CSS_URL.findall(text) + _CSS_IMPORT.findall(text)
    elif kind == 'js':
        found += _JS_STR.findall(text)
    return {k for u in found if (k := _keep(u))}


def safe_rel(rel):
    """Відносний шлях ВСЕРЕДИНІ ітерації, або None (ревʼю 1.51: path traversal).

    `manifest.json` і посилання сторінок — чужі дані: `..`, абсолютний шлях,
    `%2e%2e` чи зворотна коса не сміють вивести запис за теку ітерації — інакше
    «превʼю колеги» перезаписало б ~/.zshrc чи ~/.ssh/authorized_keys."""
    if not isinstance(rel, str):
        return None
    r = unquote(rel).replace('\\', '/')
    if not r or r.startswith('/') or re.match(r'^[A-Za-z]:', r):
        return None
    r = posixpath.normpath(r)
    if r in ('.', '..') or r.startswith('../'):
        return None
    return r


def _kind(path):
    ext = path.rsplit('.', 1)[-1].lower() if '.' in path else ''
    return {'html': 'html', 'htm': 'html', 'css': 'css', 'js': 'js', 'mjs': 'js'}.get(ext)


#: Ліміти чужого превʼю (TD-36): файл і сумарний обсяг. Превʼю макета — це
#: мегабайти; гігабайти означають помилку або зловмисника.
MAX_FILE = 25 * 1024 * 1024
MAX_TOTAL = 300 * 1024 * 1024


class SameHostRedirect(urllib.request.HTTPRedirectHandler):
    """Редирект — лише в межах того самого хоста: превʼю не сміє перенаправити
    імпорт на чужий сервер (TD-36)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlparse(newurl).hostname != urlparse(req.full_url).hostname:
            raise urllib.error.HTTPError(newurl, code, f'редирект на інший хост: {newurl}', headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(SameHostRedirect, urllib.request.HTTPSHandler(context=serve._ssl_context()))


def default_fetch(url, timeout=20):
    """GET з ПЕРЕВІРЕНИМ TLS (`serve._ssl_context`: certifi, якщо є — python.org на
    macOS без нього не має кореневих сертифікатів). Без відкату на неперевірене
    зʼєднання: чужий вміст качаємо лише з перевіреним сертифікатом."""
    req = urllib.request.Request(url, headers={'User-Agent': 'design-canvas-import'})
    try:
        with _OPENER.open(req, timeout=timeout) as r:  # noqa: S310
            data = r.read(MAX_FILE + 1)
            if len(data) > MAX_FILE:
                raise FetchError(f'{url}: понад {MAX_FILE // (1024 * 1024)} МБ')
            return data
    except urllib.error.HTTPError as e:
        raise FetchError(f'{e.code} {url}', code=e.code) from None
    except (urllib.error.URLError, socket.timeout, OSError) as e:
        raise FetchError(f'{url}: {getattr(e, "reason", e)}') from None


# Чуже в ітерації превʼю — не макет: кадри «Огляду», бандли коментатора й оболонки.
_SKIP = ('_frames/', 'comment-layer/', 'shell/')


def crawl(base, it, entries, fetch, limit=3000):
    """BFS за посиланнями в межах `<it>/`. → ({rel: bytes}, биті, не скачані).

    «Биті» — 404 від самого превʼю: їх немає й у колеги (на boss-interface it15
    так виглядали 200 шрифтів із вшитого beasties CSS — на вигляд не впливає).
    «Не скачані» — мережа/таймаут: справжній збій імпорту."""
    files, broken, failed, queue, seen = {}, [], [], list(entries), set(entries)
    total = 0
    while queue and len(seen) <= limit:
        rel = queue.pop(0)
        try:
            data = fetch(f'{base}/{it}/{rel}')
        except FetchError as e:
            (broken if e.code == 404 else failed).append(rel)
            continue
        if len(data) > MAX_FILE:
            failed.append(rel)
            continue
        total += len(data)
        if total > MAX_TOTAL:
            raise ImportError_(f'превʼю важче за {MAX_TOTAL // (1024 * 1024)} МБ — імпорт зупинено')
        files[rel] = data
        k = _kind(rel)
        if not k:
            continue
        for u in refs(data.decode('utf-8', 'replace'), k):
            nxt = safe_rel(posixpath.join(posixpath.dirname(rel), u))
            if nxt is None or nxt.startswith(_SKIP) or nxt in seen:
                continue
            seen.add(nxt)
            queue.append(nxt)
    return files, sorted(broken), sorted(failed)


def _next_ids(its):
    nums = [int(m.group(1)) for i in its if (m := re.match(r'^it(\d+)$', i.get('id', '')))]
    n = max(nums, default=0) + 1
    return f'it{n}', f'it{n + 1}'


def import_iteration(task_dir, url, src_it=None, fetch=default_fetch, dry_run=False):
    base = url.rstrip('/')
    try:
        man = json.loads(fetch(f'{base}/manifest.json'))
    except (FetchError, ValueError) as e:
        raise ImportError_(f'manifest.json не прочитано ({e}) — це точно превʼю канваса?') from None
    iters = man.get('iters') or []
    if not iters:
        raise ImportError_('у manifest.json немає ітерацій')
    if src_it is None:
        src_it = max(iters, key=lambda i: int(i.get('num') or 0))['id']
    elif not any(i.get('id') == src_it for i in iters):
        raise ImportError_(f'у превʼю немає {src_it}; є: {", ".join(i["id"] for i in iters)}')
    pages = [p for p in man.get('pages') or [] if p.get('it') == src_it]
    if not pages:
        raise ImportError_(f'у {src_it} немає опублікованих сторінок')
    entries = []
    for p in pages:
        path = safe_rel(p.get('path'))
        rel = safe_rel(posixpath.relpath(path, src_it)) if path and path.startswith(f'{src_it}/') else None
        if rel is None:
            raise ImportError_(f'підозрілий шлях сторінки в manifest.json: {p.get("path")!r} — імпорт зупинено')
        entries.append(rel)
    files, broken, failed = crawl(base, src_it, entries, fetch)
    unstripped = []
    for rel in entries:
        if rel in files:
            clean, ok = strip_publish(files[rel].decode('utf-8'))
            files[rel] = clean.encode('utf-8')
            if not ok:
                unstripped.append(rel)
    tree = outline_tree(man.get('outline') or [], src_it)
    meta = serve.load_meta({'dir': task_dir})
    its = meta.setdefault('iterations', [])
    new_id, work_id = _next_ids(its)
    report = {'source_it': src_it, 'imported': new_id, 'working': work_id, 'files': len(files),
              'broken': broken, 'failed': failed, 'unstripped': unstripped, 'pages': len(entries)}
    if dry_run:
        return report
    root = os.path.join(task_dir, 'iterations', new_id)
    real_root = os.path.realpath(root)
    for rel, data in files.items():
        dst = os.path.join(root, *rel.split('/'))
        # Друга межа, незалежна від `safe_rel`: файл мусить лягти ВСЕРЕДИНУ теки.
        if not os.path.realpath(dst).startswith(real_root + os.sep):
            raise ImportError_(f'шлях виходить за теку ітерації: {rel!r}')
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, 'wb') as fh:
            fh.write(data)
    if tree:
        pm.write_pages(root, tree)
    serve.copy_mockup(root, os.path.join(task_dir, 'iterations', work_id))
    host = urlparse(base).hostname or 'preview'
    stamp = time.strftime('%d.%m.%Y %H:%M')
    its.append({'id': new_id, 'date': stamp, 'published': False,
                'note': f'імпорт з превʼю ({src_it})', 'author': 'превʼю колеги',
                'author_key': f'preview:{host}', 'from_preview': f'{base} · {src_it}'})
    its.append(serve._stamp_author({'id': work_id, 'date': stamp, 'published': False,
                                    'note': f'робоча копія імпорту {new_id}', 'from': new_id}))
    serve.save_meta({'dir': task_dir}, meta)
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(prog='import_preview.py',
                                 description='Імпорт ітерації з опублікованого превʼю колеги в задачу.')
    ap.add_argument('url', help='адреса превʼю, напр. https://pv-12345678-abc.vercel.app')
    ap.add_argument('--task-dir', required=True, help='тека задачі (де лежить iterations/)')
    ap.add_argument('--it', dest='src_it', metavar='itN', help='яку ітерацію превʼю взяти (типово — останню)')
    ap.add_argument('--dry-run', action='store_true', help='лише показати, що буде імпортовано')
    a = ap.parse_args(argv)
    if not os.path.isdir(os.path.join(a.task_dir, 'iterations')):
        print(f'error: у {a.task_dir} немає iterations/ — це тека задачі?', file=sys.stderr)
        return 2
    try:
        rep = import_iteration(a.task_dir, a.url, a.src_it, dry_run=a.dry_run)
    except ImportError_ as e:
        print(f'error: {e}', file=sys.stderr)
        return 2
    print(json.dumps(rep, ensure_ascii=False))
    if rep['failed']:
        print(f'⛔ не скачано {len(rep["failed"])} файлів (мережа) — повтори імпорт: '
              f'{", ".join(rep["failed"][:5])}', file=sys.stderr)
    if rep['broken']:
        print(f'· {len(rep["broken"])} посилань битих і в самому превʼю (404) — у колеги так само, '
              f'на вигляд не впливає', file=sys.stderr)
    if rep['unstripped']:
        print(f'⚠ без вставок публікації (стара публікація?): {", ".join(rep["unstripped"])}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
