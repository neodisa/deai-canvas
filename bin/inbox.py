#!/usr/bin/env python3
"""Design Canvas · inbox: коментарі-фідбек по поточній задачі.

Для Claude:
  `python3 bin/inbox.py` — усе до відпрацювання скопом;
  `python3 bin/inbox.py resolve <id> --reason "що зроблено"` — закрити пін(и);
  `python3 bin/inbox.py -h` — довідка;
  `python3 bin/inbox.py --task <id> …` — про названу задачу, а не поточну.
ДВА джерела:
  • ЛОКАЛЬНІ · мені — фідбек користувача мені, у локальному файлі
    (`<task>/.dc-local-comments.json`), НЕ в Supabase. Пини фіолетові, без номера.
  • ПРОЄКТ — коментарі колег + історія з Supabase (канал tasks.json `comment_project`).
Ітерацію кожного коментаря несе meta.version → показуємо тегом [itN].

Чому тут argparse (fb-22092026-6aed32, 22.09.2026): до цього аргументів не
читав ніхто, і `inbox.py --help` мовчки друкував повний дамп коментарів. Спроба
подивитись, як закрити пін, закінчувалась ручною правкою
`.dc-local-comments.json`, бо команди для цього не було видно. Тому невідомий
аргумент тепер — помилка з usage, а не тиша: тихе ігнорування і було вадою.
"""
import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import quote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'app'))
from serve import (load_tasks, supabase_pins, comment_channel,  # noqa: E402
                   task_iterations, iter_num, machine_identity,
                   iteration_is_mine, supabase_config, _ssl_context,
                   task_for, UnknownTask, TaskNotHere)
from atomic_io import atomic_write_json  # noqa: E402

LOCAL_FILE = '.dc-local-comments.json'
#: Коротший префікс — уже не адреса піна, а випадковий збіг. inbox друкує 8.
MIN_PREFIX = 6
#: Скільки початку outerHTML показувати в якорі (fb-22092026-4460ae).
HTML_HEAD = 80
TS_FORMAT = '%d.%m.%Y %H:%M'
#: Класи, які comment-layer САМ вішає на елементи сторінки: підсвітка під
#: курсором, мультивибір, спалах. outerHTML знімається з живого елемента, тож
#: підсвітка може в нього потрапити — і селектор `.madd-cav.cl-hl` шукав би в
#: коді макета клас, якого там немає. У рядку `html:` знімок лишається як є.
CL_OWN_CLASSES = frozenset({'cl-hl', 'cl-msel', 'cl-el-flash'})


def _it(p):
    m = p.get('meta') or {}
    return m.get('version') or '—'


def _local_path(task):
    return os.path.join(task['dir'], LOCAL_FILE)


def read_local(task):
    f = _local_path(task)
    try:
        return json.loads(open(f, encoding='utf-8').read()) if os.path.isfile(f) else []
    except (OSError, ValueError):
        return []


def _band(w):
    """Назва розкладки за шириною екрана, на якій поставлено пін.

    Навіщо: коментар «цей список має бути вертикально» без ширини
    двозначний — невідомо, дизайнер дивився мобільну версію чи десктопну, і
    правиться не те (саме так і сталось, пін 0265f0fa).

    ⚠️ Сама ширина в пінах була ВЖЕ — comment-layer пише `meta.viewport`
    від початку. Не було рівно цього рядка у виводі. Тому це виправлення
    працює і на всій історії пінів, а не лише на нових.

    Межі — ті самі, що в макетах: 768 і 1024.
    """
    try:
        w = int(w)
    except (TypeError, ValueError):
        return '?'
    if w < 768:
        return 'мобільна'
    if w < 1024:
        return 'планшет'
    return 'десктоп'


# ---------- якір піна ----------

class _FirstTag(HTMLParser):
    """Лише ПЕРШИЙ відкривальний тег: решта outerHTML — нащадки, не корінь."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.attrs = None

    def handle_starttag(self, tag, attrs):
        if self.attrs is None:
            self.attrs = attrs


def _snapshot_html(p):
    """outerHTML зі знімка піна, з обох каналів.

    Імена ключів різні НЕ випадково: локальний файл пише comment-layer у своїй
    формі (`htmlSnapshot`), а Supabase віддає рядок таблиці (`html_snapshot`,
    jsonb з `text` і `outerHTML`). Зчитати лише одне — означало б мовчки
    загубити якір на половині пінів.

    ⛔ `meta.shot` (base64-картинка на десятки КБ) сюди не потрапляє і
    не мусить: це не розмітка, а мініатюра для людини.
    """
    snap = p.get('htmlSnapshot') or p.get('html_snapshot') or {}
    html = snap.get('outerHTML') if isinstance(snap, dict) else None
    return html if isinstance(html, str) else ''


def root_selector(html):
    """Селектор кореневого елемента піна (`.a.b`) з `class` ПЕРШОГО тегу.

    Навіщо (fb-22092026-4460ae, 22.09.2026): якір друкувався тегом і шляхом
    індексів, а шлях рахується на сторінці, де канвас додає власну обгортку,
    — індекси не збігались із DOM превʼю, і сесії йшли читати JSON руками
    (елементом виявився `.madd-cav`, а за шляхом виходила зовсім інша нода).
    Клас і початок outerHTML впізнають елемент за секунду.

    Розбір — `html.parser`, а не регекс: значення атрибута в лапках може
    містити `>` чи `class=` (data-атрибут), і регекс по `[^>]*` зрізав би тег
    посередині або взяв би чужий «class».

    Спецсимволи (`md:flex`, `w-1/2`) НЕ екрановано навмисно: рядок для пошуку
    по коду макета, а не для querySelector. Порожній `class=""` — порожній
    рядок, і тоді селектора у виводі немає зовсім.
    """
    if not html:
        return ''
    parser = _FirstTag()
    try:
        parser.feed(html)
    except Exception:  # noqa: BLE001 — зіпсований знімок не валить увесь інбокс
        return ''
    cls = next((v for k, v in (parser.attrs or []) if k == 'class'), None) or ''
    return ''.join('.' + t for t in cls.split() if t not in CL_OWN_CLASSES)


def html_head(html, limit=HTML_HEAD):
    """Перші ~80 символів outerHTML одним рядком.

    Пробіли схлопнуто: відформатована розмітка починається з переносів і
    відступів, і без цього у 80 символів влазив би один тег. `data:`-URI
    згорнуто: інлайн-картинка в `src` інакше зʼїла б увесь фрагмент base64-шумом.
    """
    s = re.sub(r'\s+', ' ', html or '').strip()
    s = re.sub(r'data:[^\s"\'<>)]{16,}', 'data:…', s)
    return s if len(s) <= limit else s[:limit] + '…'


# ---------- «станом на» ----------

def _parse_ts(s):
    try:
        return datetime.strptime(s.strip(), TS_FORMAT)
    except (AttributeError, TypeError, ValueError):
        return None


def newest_ts(pins):
    """Час найновішого піна каналу — max за РОЗІБРАНИМ часом, не за рядком.

    Навіщо (fb-15092026-8221e6, 15.09.2026): записка казала «inbox показує не
    всі піни — 27 замість 36, схоже на обрізання». Діагноз НЕВІРНИЙ, перевірено:
    обрізання в коді немає, а всі 9 «загублених» пінів створені через 0–5
    хвилин ПІСЛЯ запуску inbox.py — дизайнерка коментувала наживо. Справжня
    дірка — вивід не казав, СТАНОМ НА КОЛИ він, тож друге читання, що
    розійшлось із першим, виглядало як баг. Тепер кожен вивід несе свій час і
    час найновішого піна по каналу: два читання порівнюються самі.

    ⚠️ `ts` — рядок 'DD.MM.YYYY HH:MM' (і в локальних, і в проєктних), тож
    лексикографічний max ставить '15.09' вище за '02.10'. Тому лише через
    datetime. Нерозбірні рядки ігноруються для max, а не валять вивід.
    """
    parsed = [d for d in (_parse_ts(p.get('ts')) for p in pins) if d]
    return max(parsed) if parsed else None


def _newest_line(pins):
    d = newest_ts(pins)
    return (f'  найновіший пін: {d.strftime(TS_FORMAT)}' if d
            else '  найновіший пін: — (немає пінів із часом)')


# ---------- список ----------

def _num(p, tag):
    """Номер піна з каналом: `L#91` / `P#91`. Номери каналів незалежні
    (fb-30092026-e53eaa), тож голий «№91» неоднозначний. Локальні піни в
    канвасі номера не показують, але `meta.seq` мають — Claude посилається на нього."""
    seq = (p.get('meta') or {}).get('seq')
    return f'{tag}#{seq if seq else "?"}'


def ctx_line(ctx):
    """Те саме, що `ctxLine` у comment-layer: «Крок 2» · розділ «…» (fb-06102026-c38f46)."""
    if not isinstance(ctx, dict):
        return ''
    act = ctx.get('active') if isinstance(ctx.get('active'), list) else []
    parts = [f'«{a}»' for a in act]
    if ctx.get('heading'):
        parts.append(f'розділ «{ctx["heading"]}»')
    return ' · '.join(parts)


def pin_target(p):
    """(it, page) сторінки піна: з `meta.version` «15/me--welcome», інакше з `meta.url`."""
    m = p.get('meta') or {}
    v = str(m.get('version') or '')
    if '/' in v:
        n, page = v.split('/', 1)
        if n.isdigit():
            return f'it{n}', page
    from urllib.parse import urlparse, parse_qs
    q = parse_qs(urlparse(str(m.get('url') or '')).query)
    if q.get('it'):
        return q['it'][0], (q.get('page') or [''])[0]
    return None


def where_lookup(pins, task_id=None):
    """Віджет і двійники кожного відкритого піна (fb-30092026-e53eaa) через
    `bin/pin-where.mjs` у браузері. Повертає (мапа id→відповідь, None) або
    (None, причина) — інструмент підказки не сміє валити inbox.

    `task_id` — задачу НАЗВАНО (`--task`): браузер відкриває сторінки за
    `/t/<id>/commented?…`. Без префікса канвас віддав би ПОТОЧНУ задачу машини,
    і віджети шукались би на сторінках чужого макета."""
    items = []
    for p in pins:
        t = pin_target(p) if _is_open(p) else None
        if t and isinstance(p.get('fp'), dict):
            items.append({'id': p.get('id'), 'fp': p['fp'], 'it': t[0], 'page': t[1]})
    if not items:
        return {}, None
    url = f'http://localhost:{os.environ.get("PORT", "8765")}'
    if task_id is not None:
        url += f'/t/{quote(task_id, safe="")}'
    try:
        r = subprocess.run(['node', os.path.join(ROOT, 'bin', 'pin-where.mjs'), '--url', url],
                           input=json.dumps(items), capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as e:
        return None, str(e)
    if r.returncode != 0:
        return None, (r.stderr or r.stdout or '').strip()[:160]
    try:
        return json.loads(r.stdout or '{}'), None
    except ValueError:
        return None, 'незрозуміла відповідь pin-where'


def show_pins(pins, label, tag, where=None):
    openp = [p for p in pins if p.get('status') != 'resolved']
    resolved = len(pins) - len(openp)
    if openp:
        print(f'  {label} — {len(openp)} відкритих:')
        for p in openp:
            print(f'      • {_num(p, tag)} [{_it(p)}] {(p.get("text") or "").strip()}  '
                  f'[{(p.get("id") or "")[:8]} · {p.get("author") or ""}]')
            ctx = ctx_line((p.get('meta') or {}).get('ctx'))
            if ctx:
                print(f'          ↳ де: {ctx}')
            w = (where or {}).get(p.get('id'))
            if w is not None:
                if not w.get('found'):
                    print('          ↳ на сторінці не знайдено (інший стан чи елемент змінився)')
                else:
                    if w.get('widget'):
                        print(f'          ↳ віджет: {w["widget"]}')
                    tw = w.get('twins') or []
                    if tw:
                        print(f'          ↳ ще {len(tw)} таких самих: ' + ', '.join(f'«{x}»' for x in tw))
            vp = ((p.get('meta') or {}).get('viewport') or {})
            if vp.get('w'):
                print(f'          ↳ ширина: {_band(vp["w"])} · {vp["w"]}×{vp.get("h")}')
            fp = p.get('fp') or {}
            if fp:
                anchor = (fp.get('text') or '').strip().replace('\n', ' ')[:50]
                path = ' > '.join((fp.get('path') or [])[-3:])
                print(f'          ↳ якір: <{fp.get("tag") or "?"}>'
                      + (f' «{anchor}»' if anchor else '')
                      + (f'  · {path}' if path else ''))
            html = _snapshot_html(p)
            sel = root_selector(html)
            if sel:
                print(f'          ↳ селектор: {sel}')
            if html:
                print(f'          ↳ html: {html_head(html)}')
    if resolved:
        print(f'  {label}: (+ {resolved} вирішених в історії)')
    return len(openp)


def resolve_task(wanted):
    """(id, задача) названої `--task` (None — поточна) або None, коли такої немає:
    тоді `error: …` уже надруковано в stderr і виходити з кодом 2.

    Невідома назва НЕ відкочується на поточну: це і була вада (fb-07102026-e627c2) —
    помилка в id тихо читала б і закривала піни чужої задачі."""
    try:
        return task_for(load_tasks(), wanted)
    except TaskNotHere:
        # Задача Є в реєстрі, але теки на цій машині нема: «порожній інбокс» тут
        # був би брехнею, а відкат на поточну — тією самою вадою.
        print(f"error: задачі '{wanted}' немає на цій машині "
              '(є в реєстрі, теки нема)', file=sys.stderr)
        return None
    except UnknownTask:
        print(f'error: немає задачі {wanted!r} у tasks.json', file=sys.stderr)
        return None


def cmd_list(where=False, task_id=None):
    got = resolve_task(task_id)
    if got is None:
        return 2
    tid, task = got
    local = read_local(task)
    try:
        proj, proj_err = supabase_pins(comment_channel(task, tid)), None
    except Exception as e:  # noqa: BLE001
        proj, proj_err = [], e
    wmap = None
    if where:
        wmap, why = where_lookup([p for p in local if isinstance(p, dict)] + list(proj),
                                 task_id)
        if why:
            print(f'⚠ --where не спрацював (канвас запущено? {why}) — друкую без віджетів\n')
    now = datetime.now()
    print(f'=== Inbox задачи «{task.get("title", tid)}» · станом на '
          f'{now.strftime("%H:%M:%S")} ({now.strftime("%d.%m.%Y")}) ===')
    print('  Піни, поставлені ПІСЛЯ цього часу, тут не видно — перед закриттям '
          'раунду перечитай.\n')
    print('-- ЛОКАЛЬНІ · мені (фідбек Claude, локальний файл, НЕ Supabase) --')
    print(_newest_line(local))
    total = show_pins(local, 'локальні', 'L', wmap)
    if not total:
        print('  (немає відкритих)')
    print('\n-- ПРОЄКТ (колеги + історія, Supabase) --')
    if proj_err is None:
        print(_newest_line(proj))
        ext = show_pins(proj, 'проєкт', 'P', wmap)
    else:
        print(f'  проєкт: (не дістати: {proj_err})')
        ext = 0
    if not ext:
        print('  (немає відкритих)')
    print(f'\nРазом до відпрацювання: {total} локальних + {ext} проєктних')
    if total + ext:
        # Підказку копіюють дослівно: без `--task` вона закрила б пін ПОТОЧНОЇ задачі.
        flag = f' --task {shlex.quote(tid)}' if task_id is not None else ''
        print(f'Закрити: python3 bin/inbox.py{flag} resolve <id> --reason "що зроблено"')
    return 0


# ---------- resolve ----------

def working_iteration(its, my_key=''):
    """Та сама робоча ітерація, що `state.working_iteration`: остання СВОЯ.

    ⛔ Порахована тут, а не `import state`, і це перевірено, а не про запас:
    `import state` тягне `registry`, а той на імпорті заморожує
    `TASKS_PATH` з оточення і робить `float(DC_REGISTRY_TTL_H)` — зіпсоване
    значення змінної валило б `inbox.py` ще до розбору аргументів, тобто й
    `--help`. Мережі чи запису там немає, але інбокс не мусить залежати від
    реєстру заради трьох рядків.

    Ціна копії — розсинхрон двох правил, тому їх звіряє тест
    (`tests/test_inbox.py`, парний інваріант із `state.working_iteration`).
    """
    if not its:
        return None
    mine = [it for it in its if iteration_is_mine(it, my_key)]
    return (mine or its)[-1]


def default_iteration(task):
    """Номер робочої ітерації для `resolvedV`, або None, якщо його немає."""
    work = working_iteration(task_iterations(task), machine_identity()[1])
    n = iter_num(work['id']) if work else ''
    return int(n) if str(n).isdigit() else None


def _match(pins, prefix):
    return [p for p in pins if (p.get('id') or '').lower().startswith(prefix)]


def _is_open(p):
    return p.get('status') != 'resolved'


def _cand(p):
    return f'{(p.get("id") or "")[:8]} «{(p.get("text") or "").strip()[:40]}»'


def find_target(prefix, local, project_loader):
    """Знайти ОДИН відкритий пін за префіксом.

    → ('local'|'project', пін) · ('closed', [закриті збіги]) · (None, чому ні).

    Спершу локальні: вони без мережі, і закриття своїх пінів не мусить
    залежати від VPN. Проєктні тягнемо лише якщо локально відкритого збігу
    немає. Уже закритий — окремий результат ('closed'), а не «не знайдено»:
    сказати «немає такого піна» про пін, що є і закритий, — неправда.
    """
    hits = [p for p in _match(local, prefix) if _is_open(p)]
    if len(hits) > 1:
        return None, ('неоднозначний префікс, кандидати: '
                      + '; '.join(_cand(p) for p in hits))
    if hits:
        return 'local', hits[0]
    try:
        project = project_loader()
    except Exception as e:  # noqa: BLE001
        # ⛔ Не «не знайдено»: ми не знаємо, чи він там є.
        closed = [p for p in _match(local, prefix) if not _is_open(p)]
        if closed:
            return 'closed', closed
        return None, f'локально немає, а проєкт недоступний ({e})'
    hits = [p for p in _match(project, prefix) if _is_open(p)]
    if len(hits) > 1:
        return None, ('неоднозначний префікс, кандидати: '
                      + '; '.join(_cand(p) for p in hits))
    if hits:
        return 'project', hits[0]
    closed = [p for p in _match(local, prefix) + _match(project, prefix)
              if not _is_open(p)]
    if closed:
        return 'closed', closed
    return None, 'не знайдено серед пінів поточної задачі'


def write_local_resolved(path, ids, n, reason, now_ms):
    """Переписати локальний файл: закрити названі піни, решту не чіпати.

    Файл перечитується ТУТ, безпосередньо перед записом, а не береться з
    пошуку: між пошуком і записом міг піти запит у Supabase, а вкладка канваса
    — дописати пін. Вікно read-modify-write звужене до мілісекунд, але НЕ
    закрите: спільного лока між цим процесом і вкладкою немає.

    Прямий запис безпечний щодо вкладки: `app/vendor/local-adapter.js` перед
    своїм POST зливає тристоронньо, і пін, якого вкладка не міняла, лишається
    таким, як на диску, тобто закритим.

    Поля міняються на місці — порядок ключів і решта полів ті самі; `indent=1`
    — як у `serve._local_comments_post`, інакше кожне закриття з CLI давало б
    діф на весь файл.
    """
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    done, already = [], []
    for p in data:
        if not (isinstance(p, dict) and p.get('id') in ids):
            continue
        if not _is_open(p):
            # Закрили між пошуком і записом (вкладка): чужу причину не затираємо.
            already.append(p['id'])
            continue
        p['status'] = 'resolved'
        p['resolvedV'] = n
        p['resolveReason'] = reason
        meta = p.get('meta') if isinstance(p.get('meta'), dict) else {}
        meta['resolvedAt'] = now_ms
        p['meta'] = meta
        done.append(p['id'])
    if done:
        atomic_write_json(path, data, indent=1)
    return done, already


def patch_project_pin(pin_id, n, reason):
    """PATCH піна в Supabase — ті самі поля й типи, що вручну 15.09.2026.

    Тут, а не в `serve.py`: сервер правлять паралельно, а закриття пінів —
    справа CLI, не HTTP-обробника.

    ⚠️ `meta.resolvedAt` сюди НЕ їде: PostgREST міняє jsonb цілком, а в `meta`
    лежать `shot` (base64) і `shotUrl`. Переписати весь meta заради однієї мітки
    — ризикнути затерти те, що дописав браузер. Наслідок: на вкладці «Closed»
    comment-layer такий пін сортується як закритий без часу.

    ⚠️ `Prefer: return=minimal` дає 204 і тоді, коли жоден рядок не збігся.
    id щойно прочитано з тієї самої таблиці, а `cl_update` — `using (true)`,
    тож тихий нуль можливий лише тоді, коли пін видалили між читанням і
    записом. HTTP-помилка ж підіймається з `urlopen` гучно.
    """
    url, key = supabase_config()
    req = urllib.request.Request(
        f'{url}/rest/v1/comments?id=eq.{quote(pin_id, safe="")}',
        data=json.dumps(project_body(n, reason)).encode('utf-8'),
        method='PATCH',
        headers={'apikey': key, 'Authorization': f'Bearer {key}',
                 'Content-Type': 'application/json', 'Prefer': 'return=minimal'})
    with urllib.request.urlopen(req, timeout=10, context=_ssl_context()) as res:
        return res.status


def project_body(n, reason):
    return {'status': 'resolved', 'resolved_v': n, 'resolve_reason': reason}


def cmd_resolve(a):
    """`resolve`: закрити пін(и) з причиною.

    Навіщо: CLI для цього не було, і сесії щоразу писали ручні скрипти або
    правили `.dc-local-comments.json` руками (fb-22092026-6aed32).

    Уже закритий пін — «сказати й пропустити», і код виходу він НЕ псує:
    повторний прогін тієї самої команди після часткового збою мусить пройти,
    а не впасти на пінах, які вже в потрібному стані. Ненульовий код — рівно
    коли хоч один пін лишився відкритим: не знайдено, неоднозначно, мережа.
    """
    got = resolve_task(a.task)
    if got is None:
        return 2
    tid, task = got
    n = a.it if a.it is not None else default_iteration(task)
    if n is None:
        print('⚠ не вдалося визначити номер робочої ітерації — задай --it N')
        return 1
    reason = a.reason.strip()
    path = _local_path(task)
    local = read_local(task)
    local = [p for p in local if isinstance(p, dict)] if isinstance(local, list) else []
    cache = {}

    def project_loader():
        # Помилку теж запамʼятовуємо: без VPN кожен наступний префікс інакше
        # чекав би свій таймаут заново.
        if 'pins' not in cache:
            try:
                cache['pins'] = supabase_pins(comment_channel(task, tid))
            except Exception as e:  # noqa: BLE001
                cache['pins'] = e
        if isinstance(cache['pins'], Exception):
            raise cache['pins']
        return cache['pins']

    failed = 0
    local_ids, project_pins, seen = [], [], set()
    for raw in a.prefixes:
        prefix = raw.strip().lower()
        kind, found = find_target(prefix, local, project_loader)
        if kind is None:
            print(f'✗ {raw}: {found}')
            failed += 1
        elif kind == 'closed':
            # Номер ітерації тут НЕ друкуємо: `resolvedV`, який ставить сам
            # comment-layer, — його внутрішній лічильник версій, а не Іт.N, і
            # «Іт.3» про такий пін було б неправдою.
            for p in found:
                print(f'⏭ {(p.get("id") or "")[:8]}: уже закритий'
                      f' («{p.get("resolveReason") or p.get("resolve_reason") or "—"}»)'
                      ' — пропускаю')
        elif found['id'] in seen:
            continue
        else:
            seen.add(found['id'])
            (local_ids if kind == 'local' else project_pins).append(found)

    now_ms = int(time.time() * 1000)
    if local_ids:
        ids = [p['id'] for p in local_ids]
        if a.dry_run:
            for p in local_ids:
                print(f'[dry-run] {path}: {p["id"][:8]} ← status=resolved, '
                      f'resolvedV={n}, resolveReason={json.dumps(reason, ensure_ascii=False)}, '
                      f'meta.resolvedAt={now_ms}')
        else:
            try:
                done, already = write_local_resolved(path, set(ids), n, reason, now_ms)
            except (OSError, ValueError) as e:
                done, already = [], []
                print(f'✗ локальний файл не переписано ({e})')
            for p in local_ids:
                if p['id'] in done:
                    print(f'✓ {p["id"][:8]} закрито (локальний, Іт.{n}): «{reason}»')
                elif p['id'] in already:
                    print(f'⏭ {p["id"][:8]}: уже закрили з вкладки, поки йшов пошук'
                          ' — пропускаю')
                else:
                    print(f'✗ {p["id"][:8]}: не закрито в локальному файлі')
                    failed += 1
    for p in project_pins:
        if a.dry_run:
            url, _ = supabase_config()
            print(f'[dry-run] PATCH {url}/rest/v1/comments?id=eq.'
                  f'{quote(p["id"], safe="")} '
                  f'{json.dumps(project_body(n, reason), ensure_ascii=False)}')
            continue
        try:
            patch_project_pin(p['id'], n, reason)
            print(f'✓ {p["id"][:8]} закрито (проєкт, Іт.{n}): «{reason}»')
        except Exception as e:  # noqa: BLE001 — кожен пін звітує сам за себе
            print(f'✗ {p["id"][:8]}: Supabase не прийняв ({e})')
            failed += 1
    if a.dry_run:
        print('[dry-run] нічого не записано')
    return 1 if failed else 0


# ---------- аргументи ----------

EPILOG = """\
Закрити пін (id — перші символи з виводу, «[3f2a9c1b · автор]»):
  python3 bin/inbox.py resolve 3f2a9c1b --reason "кнопку перенесено в шапку"
  python3 bin/inbox.py resolve 3f2a9c 7d41e0 --reason "..." --it 4 --dry-run
Паралельні сесії: `current` один на машину, тож називай свою задачу — `--task` стоїть
ПЕРЕД підкомандою (після неї — помилка):
  python3 bin/inbox.py --task bf360
  python3 bin/inbox.py --task bf360 resolve 3f2a9c1b --reason "..."
Подробиці: python3 bin/inbox.py resolve -h
"""


def build_parser():
    ap = argparse.ArgumentParser(
        prog='inbox.py',
        description='Коментарі-піни поточної (або названої --task) задачі: '
                    'локальні (мені) + проєктні (Supabase). Без аргументів — '
                    'перелік відкритих.',
        epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--task', metavar='ID',
                    help='задача з tasks.json замість поточної — для паралельних сесій '
                         '(перед підкомандою); невідомий id чи задача без теки на цій '
                         'машині — помилка, а не поточна задача')
    ap.add_argument('--where', action='store_true',
                    help='для кожного відкритого піна — віджет і скільки таких самих '
                         'елементів на сторінці (браузер; потрібен запущений канвас)')
    sub = ap.add_subparsers(dest='cmd', metavar='{resolve}')
    rp = sub.add_parser(
        'resolve', help='закрити пін(и) з причиною',
        description='Закрити відкриті піни поточної (або названої --task) '
                    'задачі. Шукає спершу локальні, потім проєктні; '
                    'неоднозначний префікс — відмова з переліком кандидатів, '
                    'уже закритий — пропуск.',
        epilog='Приклад: python3 bin/inbox.py resolve 3f2a9c1b '
               '--reason "кнопку перенесено в шапку"',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    rp.add_argument('prefixes', nargs='+', metavar='ID',
                    help=f'префікс id піна, не коротший за {MIN_PREFIX} символів')
    rp.add_argument('--reason', required=True,
                    help='що зроблено — обовʼязково: без причини comment-layer '
                         'показує «resolved manually», і дизайнер не знає, що змінилось')
    rp.add_argument('--it', type=int, metavar='N',
                    help='номер ітерації, в якій закрито (типово — робоча: остання своя)')
    rp.add_argument('--dry-run', action='store_true',
                    help='надрукувати, що було б записано, нічого не міняючи')
    return ap, rp


def main(argv=None):
    ap, rp = build_parser()
    a = ap.parse_args(argv)
    if a.cmd == 'resolve':
        if not a.reason.strip():
            rp.error('--reason порожній: напиши, що зроблено')
        if a.it is not None and a.it < 1:
            rp.error('--it: номер ітерації — ціле від 1')
        short = [p for p in a.prefixes if len(p.strip()) < MIN_PREFIX]
        if short:
            rp.error(f'префікс коротший за {MIN_PREFIX} символів: {", ".join(short)}')
        return cmd_resolve(a)
    return cmd_list(where=a.where, task_id=a.task)


if __name__ == '__main__':
    sys.exit(main())
