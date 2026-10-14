#!/usr/bin/env python3
"""Імпорт ітерації з ЧУЖОГО опублікованого превʼю в задачу — для Claude (fb-29092026-210ec1).

  import_preview.py --task-dir D <url превʼю> [--it itN] [--dry-run]

Колега публікує ту саму задачу у свій Vercel-проєкт — і його ітерації живуть лише
там. Раніше їх переносили руками: зняти сніпет коментатора й гейт, відновити
title з `__origTitle`. Ця команда:
  1. читає `<url>/manifest.json` (джерело правди оболонки превʼю), а для превʼю
     до 02.09.2026 — дані `var D` з обгортки: ітерації, сторінки, дерево
     `outline`; без `--it` бере ОСТАННЮ. Дерево зі старої обгортки відновлюється
     НАБЛИЖЕНО — за глибиною рядків (теки-організатори `isGroup` у ній існували,
     але в превʼю не публікувались);
  2. збирає файли за посиланнями зі сторінок, CSS і JS — статичний хостинг
     переліку файлів не віддає, тож інакше спільні assets/icons/fonts і ліниві
     чанки SPA не знайти; чого не знайшлось — каже переліком, а не мовчить;
  3. вирізає зі сторінок вставки публікації (сніпет коментатора, гейт,
     нейтральний title) — рівно ті, що вставляє `serve._publish`, і ті, що вставляли
     його старі версії. ⛔ Гейт несе ПАРОЛЬ превʼю відкритим текстом: сторінка, з якої
     гейт зняти не вдалось, не пишеться — імпорт зупиняється ще до запису;
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
# Сніпет коментатора ДО 27.08.2026 (6ced2ae) починався тегом бібліотеки Supabase —
# спершу без `onerror` (466b172…38b4080), потім з ним (5ed9bf7). Префікс без `>` бере
# обидва. Превʼю тієї доби ще живі, а гейт у них той самий (`_gate_end` не залежить
# від версії). Старі шаблони стерегтиме `OldTemplates` — вони там БУКВАЛЬНІ.
_OLD_SNIPPET_START = '\n<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"'
_SNIPPET_STARTS = (_SNIPPET_START, _OLD_SNIPPET_START)
# Той самий маркер, за яким `serve._inject_gate` розпізнає, що гейт уже є.
_GATE_MARK = 'id="authgate"'
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
    found = [i for i in (html.find(a) for a in _SNIPPET_STARTS) if i >= 0]
    start = min(found) if found else -1
    end_mark = _gate_end()
    end = html.find(end_mark, start if start >= 0 else 0)
    if start < 0 or end < 0:
        return html, False
    m = _ORIG_RE.search(html, start, end + len(end_mark))
    out = html[:start] + html[end + len(end_mark):]
    if m and _NEUTRAL_TITLE in out:
        out = out.replace(_NEUTRAL_TITLE, f'<title>{_title_source(json.loads(m.group(1)))}</title>', 1)
    return out, True


def _title_source(text):
    """Назва зі `__origTitle` → вміст `<title>` як ВИХІДНИЙ КОД. Чинна публікація кладе туди
    РОЗЕКРАНОВАНИЙ текст (`document.title` — текст, не розмітка: `serve._inject_gate`), тож
    `<` і `>` мусять стати сутностями — інакше `A </title><b>x</b>` стає справжньою розміткою в
    імпортованій ітерації. Сирий `&` теж екранується, але лише коли це не вже готова сутність
    (`&amp;`, `&#39;`): превʼю, опубліковані ДО цього контракту, несуть у `__origTitle` СИРИЙ
    вихідний текст, і їхні сутності не можна подвоювати (`R&amp;D` → `R&amp;amp;D`)."""
    return re.sub(r'&(?!#?\w+;)', '&amp;', text.replace('<', '&lt;').replace('>', '&gt;'))


def _depth(v):
    """Глибина рядка зі ЧУЖИХ даних: лише невідʼємне ціле, не глибше за
    `pm.MAX_DEPTH - 1` (щоб дерево з рядків не вийшло за межу вкладеності); сміття → 0."""
    v = v if isinstance(v, int) and not isinstance(v, bool) else 0
    return max(0, min(v, pm.MAX_DEPTH - 1))


def outline_tree(outline, it):
    """Пласкі рядки `manifest.outline` однієї ітерації → дерево pages.json."""
    tree, stack = [], []
    for row in outline:
        if not isinstance(row, dict) or row.get('it') != it:
            continue
        node = {'id': row.get('key'), 'name': row.get('name') or row.get('key'), 'kind': row.get('kind') or 'page'}
        depth = _depth(row.get('depth'))
        del stack[depth:]
        if stack:
            stack[-1].setdefault('children', []).append(node)
        else:
            tree.append(node)
        stack.append(node)
    return tree


_LEGACY_D = 'var D='
_LEGACY_BAD = 'дані старої обгортки (var D) мають несподіваний вигляд'


def legacy_manifest(d):
    """Дані обгортки превʼю старого формату (04.08–02.09.2026, `var D` інлайном) →
    маніфест того вигляду, що читає імпорт (fb-09102026-8b12a5). Номер ітерації — з її
    id; тека сторінки = її id (`pm.page_rel`), корінь ітерації — неявна `main`.
    Дерево відновлюється НАБЛИЖЕНО — за `depth` рядків: теки-організатори (`isGroup`)
    в обгортці існували, але в превʼю не публікувались, тож їх не відновити.

    Дані ЧУЖІ: форма перевіряється тут. Не обʼєкт чи не списки — ValueError (викликач
    скаже «несподіваний вигляд»); елементи не того типу й сторінки без рядкових
    id/it пропускаються; `depth` — через `_depth`; номер ітерації — до 9 цифр (id з
    тисячами цифр не валить `int()`)."""
    if not isinstance(d, dict):
        raise ValueError('D не обʼєкт')
    iters_raw, pages_raw = d.get('iters') or [], d.get('pages') or []
    if not isinstance(iters_raw, list) or not isinstance(pages_raw, list):
        raise ValueError('iters/pages не списки')
    iters = []
    for it in iters_raw:
        if not isinstance(it, dict) or not isinstance(it.get('id'), str):
            continue
        m = re.fullmatch(r'it(\d{1,9})', it['id'])
        iters.append({'id': it['id'], 'num': int(m.group(1)) if m else 0})
    pages, outline = [], []
    for p in pages_raw:
        if not isinstance(p, dict):
            continue
        it, out = p.get('it'), p.get('id')
        if not (isinstance(it, str) and it and isinstance(out, str)):
            continue
        key = out[len(it) + 1:] if out.startswith(f'{it}/') else (pm.IMPLICIT_ID if out == it else None)
        if not key:
            continue
        name = p['name'] if isinstance(p.get('name'), str) and p['name'].strip() else key
        path = p['path'] if isinstance(p.get('path'), str) else None
        pages.append({'it': it, 'key': key, 'name': name, 'path': path})
        outline.append({'it': it, 'key': key, 'name': name, 'kind': 'page', 'depth': _depth(p.get('depth'))})
    return {'iters': iters, 'pages': pages, 'outline': outline}


def load_manifest(base, fetch):
    """(маніфест, формат). Новий формат — `manifest.json`; на його 404 (і лише 404:
    мережевий збій — не привід гадати) — `var D` з обгортки старого формату.
    ⛔ `PW=` (пароль превʼю відкритим текстом у старій обгортці) не читаємо: розбираємо
    лише обʼєкт після `var D=` (`raw_decode`), а не регексом до `,PW=` — назва сторінки
    може містити будь-що."""
    try:
        man = json.loads(fetch(f'{base}/manifest.json'))
    except FetchError as e:
        if e.code != 404:
            raise ImportError_(f'manifest.json не прочитано ({e}) — це точно превʼю канваса?') from None
    except (ValueError, RecursionError) as e:
        raise ImportError_(f'manifest.json не прочитано ({e}) — це точно превʼю канваса?') from None
    else:
        if not isinstance(man, dict):
            raise ImportError_('manifest.json має несподіваний вигляд (не обʼєкт) — це точно превʼю канваса?')
        return man, 'manifest'
    try:
        html = fetch(f'{base}/').decode('utf-8', 'replace')
    except FetchError as e:
        if e.code == 404:
            raise ImportError_('ні manifest.json, ні обгортки превʼю (404) — це точно превʼю канваса?') from None
        raise ImportError_(f'manifest.json немає, а обгортку превʼю не прочитано ({e}) — повтори імпорт') from None
    at = html.find(_LEGACY_D)
    if at < 0:
        raise ImportError_('manifest.json немає, і в обгортці немає даних старого формату (var D) — '
                           'це точно превʼю канваса?')
    # `var D=` може траплятись і деінде (title задачі «Fix var D= parser», раніший
    # скрипт) — беремо перше входження, що розбирається в ОБʼЄКТ.
    d = None
    while at >= 0 and d is None:
        try:
            cand, _ = json.JSONDecoder().raw_decode(html, at + len(_LEGACY_D))
        except (ValueError, RecursionError):
            cand = None
        if isinstance(cand, dict):
            d = cand
        else:
            at = html.find(_LEGACY_D, at + 1)
    if d is None:
        raise ImportError_('дані старої обгортки (var D) не розібрано')
    try:
        return legacy_manifest(d), 'legacy-wrapper'
    except (AttributeError, TypeError, ValueError, RecursionError):
        raise ImportError_(_LEGACY_BAD) from None


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
    man, fmt = load_manifest(base, fetch)
    src = 'manifest.json' if fmt == 'manifest' else 'даних превʼю'  # звідки дані — те й називаємо в помилках
    iters = man.get('iters') or []
    if not iters:
        raise ImportError_(f'у {src} немає ітерацій')
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
            raise ImportError_(f'підозрілий шлях сторінки в {src}: {p.get("path")!r} — імпорт зупинено')
        entries.append(rel)
    # Дерево — ДО качання й запису (і в dry-run): дублікат id чи завелика глибина
    # інакше виявились би аж у `pm.write_pages`, коли файли вже лежать у теці ітерації.
    tree = outline_tree(man.get('outline') or [], src_it)
    try:
        pm.validate(tree)
    except pm.TreeError as e:
        raise ImportError_(f'дерево сторінок у {src} не пройшло перевірку ({e}) — імпорт зупинено') from None
    files, broken, failed = crawl(base, src_it, entries, fetch)
    unstripped = []
    for rel in entries:
        if rel in files:
            clean, ok = strip_publish(files[rel].decode('utf-8'))
            files[rel] = clean.encode('utf-8')
            if not ok:
                unstripped.append(rel)
    # ⛔ Запобіжник, незалежний від шаблонів: гейт несе ПАРОЛЬ превʼю відкритим текстом.
    # Якщо після зняття вставок він лишився (невідома версія шаблону) — не пишемо
    # нічого: канвас потім комітить теку ітерації в GitLab.
    for rel, data in sorted(files.items()):
        if _kind(rel) == 'html' and _GATE_MARK.encode() in data:
            raise ImportError_(f'сторінка {rel} лишилась із гейтом превʼю (пароль) — імпорт зупинено; '
                               f'онови шаблони strip_publish')
    meta = serve.load_meta({'dir': task_dir})
    its = meta.setdefault('iterations', [])
    new_id, work_id = _next_ids(its)
    report = {'source_it': src_it, 'imported': new_id, 'working': work_id, 'files': len(files),
              'broken': broken, 'failed': failed, 'unstripped': unstripped, 'pages': len(entries),
              'format': fmt}
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
    if rep.get('format') == 'legacy-wrapper':
        print('· превʼю старого формату (до 02.09.2026, без manifest.json): дерево сторінок '
              'відновлено наближено — за глибиною; теки-організатори в превʼю не публікувались',
              file=sys.stderr)
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
