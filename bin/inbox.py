#!/usr/bin/env python3
"""Design Canvas · inbox: коментарі-фідбек по поточній задачі.

Для Claude:
  `python3 bin/inbox.py` — усе до відпрацювання скопом;
  `python3 bin/inbox.py resolve <id> --reason "що зроблено"` — закрити пін(и);
  `python3 bin/inbox.py reply <id> --text "питання чи примітка"` — відповісти в гілці під пінем (0.35);
  `python3 bin/inbox.py -h` — довідка;
  `python3 bin/inbox.py --task <id> …` — про названу задачу, а не поточну.
ДВА джерела:
  • ЛОКАЛЬНІ · мені — фідбек користувача мені, у локальному файлі
    (`<task>/.dc-local-comments.json`), НЕ в Supabase. Пини фіолетові, без номера.
  • ПРОЄКТ — коментарі колег + історія: з Supabase ЛІГА (канал tasks.json `comment_project`)
    або з модуля ролі `comments` простору задачі (канал простору, `list`/`resolve` модуля).
    Хто саме — вирішує постачальник ролі `comments` ПРОСТОРУ ЗАДАЧІ (`ProjectComments`), а не
    «чи ввімкнені інтеграції»; зламаний модуль — лише локальні піни й повідомлення, а не Supabase.
    Типово показано лише командні, доручені Claude (`meta.assignee`); `--all` — усі.
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
import uuid
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import quote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'app'))
from serve import (load_tasks,  # noqa: E402
                   task_iterations, iter_num, machine_identity,
                   iteration_is_mine,
                   task_anywhere, UnknownTask, TaskNotHere, NoTask, AmbiguousTask,
                   SpaceUnavailable, ProjectComments, ModulePins, agent_line, for_agent)
import spaces  # noqa: E402
from atomic_io import atomic_write_json  # noqa: E402

LOCAL_FILE = '.dc-local-comments.json'
#: Коротший префікс — уже не адреса піна, а випадковий збіг. inbox друкує 8.
MIN_PREFIX = 6
#: Скільки початку outerHTML показувати в якорі (fb-22092026-4460ae).
HTML_HEAD = 80
TS_FORMAT = '%d.%m.%Y %H:%M'
#: Межа тексту відповіді (та сама, що в `reply` модуля `supabase-comments`) і скільки останніх відповідей друкує `show_pins`.
REPLY_MAX = 4000
REPLIES_SHOWN = 20
#: Коди `meta.shotMiss` (спека «Коментарі: відповіді») → причина, чому нема знімка. Тексти — як `cmtShotMiss_*` у `app/i18n.js`
#: (без «Без знімка:»). Невідомий код друкується як є (очищений): новий код від новішого коментатора не губимо.
SHOT_MISS = {
    'too-big': 'елемент завеликий для знімка',
    'no-lib': 'бібліотека знімків не завантажилась',
    'timeout': 'знімок не встиг',
    'render': 'знімок не вдався',
    'detached': 'елемент зник зі сторінки до збереження',
    'upload': 'знімок не завантажився в сховище',
}
#: Класи, які comment-layer САМ вішає на елементи сторінки: підсвітка під
#: курсором, мультивибір, спалах. outerHTML знімається з живого елемента, тож
#: підсвітка може в нього потрапити — і селектор `.madd-cav.cl-hl` шукав би в
#: коді макета клас, якого там немає. У рядку `html:` знімок лишається як є.
CL_OWN_CLASSES = frozenset({'cl-hl', 'cl-msel', 'cl-el-flash'})


def _it(p):
    m = p.get('meta') or {}
    v = m.get('version')
    return agent_line(v if isinstance(v, str) else str(v) if v else '', 40) or '—'


def _local_path(task):
    return os.path.join(task['dir'], LOCAL_FILE)


def read_local(task):
    f = _local_path(task)
    try:
        if not os.path.isfile(f):
            return []
        with open(f, encoding='utf-8') as fh:
            return json.load(fh)
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
    return f'{tag}#{agent_line(seq if isinstance(seq, str) else str(seq) if seq else "", 20) or "?"}'


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


#: Префікс продовження багаторядкового тексту піна: символ, якого нема в рамках виводу (`↳`, `•`), тож рядок тексту не вдасть
#: із себе гілку відповідей чи інший службовий рядок.
TEXT_CONT = '\n            │ '


def pin_text(text):
    """Текст піна для виводу: перший рядок — як є, решта — з префіксом `TEXT_CONT`; кожен рядок без керівних символів (`agent_line`).
    Текст пише будь-хто (колега, відвідувач превʼю): рядок `↳ відповіді (1):` усередині нього інакше був би невідрізним від
    справжньої гілки, а агент читає цей вивід як довіреніший за коментар."""
    s = text if isinstance(text, str) else ''
    return TEXT_CONT.join(agent_line(ln, 10000) for ln in s.strip().split('\n'))


def _reply_ts(ts):
    """`DD.MM.YYYY HH:MM` → `DD.MM HH:MM`; нерозбірний час — як є (очищений, ≤ 20)."""
    d = _parse_ts(ts)
    return d.strftime('%d.%m %H:%M') if d else agent_line(ts, 20)


#: Префікс продовження багаторядкової ВІДПОВІДІ: глибший за рядок відповіді (14 пробілів) і за продовження тексту піна (12), з тим
#: самим `│`. Рядок усередині тексту відповіді (`Іван, 01.01 10:00: …`, `↳ відповіді (9):`) так ніколи не стоїть на відступі
#: справжнього рядка відповіді чи заголовка гілки.
REPLY_CONT = '\n                │ '
#: Скільки символів тексту відповіді бачить агент (стільки ж приймає сховище); довше — з `…` в кінці.
REPLY_TEXT_MAX = 4000
REPLY_LINES_MAX = 60       # 4000 переносів інакше дали б 4000 рядків виводу на одну відповідь


def reply_line(r):
    """Відповідь для виводу: `<автор>, <ДД.ММ ГГ:ХХ>[ (ред.)]: <текст>` (відповідь агента — `AI`). Текст — ПОВНИЙ (≤ 4000, довший
    обрізається з `…`; понад `REPLY_LINES_MAX` рядків — теж `…`): людина відповідає на питання агента, і зрізати її відповідь
    мовчки не можна. Перший рядок іде в тому ж рядку,
    решта — з `REPLY_CONT`. Локальний файл пише браузер, а відповіді командного каналу — інші люди: кожен рядок проходить
    `agent_line` (без переносів і керівних символів)."""
    who = agent_line(r.get('author'), 100) or '?'
    if r.get('agent') is True:
        who = 'AI'
    elif who.strip().casefold() == 'ai':
        who = 'AI (людина)'                     # людина з імʼям «AI» не має виглядати відповіддю агента
    t = r.get('text')
    t = t.strip() if isinstance(t, str) else ''
    if len(t) > REPLY_TEXT_MAX:
        t = t[:REPLY_TEXT_MAX - 1] + '…'
    edited = ' (ред.)' if agent_line(r.get('editedTs'), 40).strip() else ''
    lines = t.split('\n')
    if len(lines) > REPLY_LINES_MAX:
        lines = lines[:REPLY_LINES_MAX - 1] + ['…']
    body = REPLY_CONT.join(agent_line(ln, REPLY_TEXT_MAX) for ln in lines)
    return f'{who}, {_reply_ts(r.get("ts"))}{edited}: {body}'


def show_pins(pins, label, tag, where=None):
    openp = [p for p in pins if p.get('status') != 'resolved']
    resolved = len(pins) - len(openp)
    if openp:
        print(f'  {label} — {len(openp)} відкритих:')
        for p in openp:
            print(f'      • {_num(p, tag)} [{_it(p)}] {pin_text(p.get("text"))}  '
                  f'[{agent_line(p.get("id") or "", 200)[:8]} · {agent_line(p.get("author") or "", 200)}]')
            ctx = agent_line(ctx_line((p.get('meta') or {}).get('ctx')), 500)
            if ctx:
                print(f'          ↳ де: {ctx}')
            replies = [r for r in p.get('replies') or [] if isinstance(r, dict)] if isinstance(p.get('replies'), list) else []
            if replies:
                print(f'          ↳ відповіді ({len(replies)}):')
                for r in replies[-REPLIES_SHOWN:]:
                    print(f'              {reply_line(r)}')
            miss = (p.get('meta') or {}).get('shotMiss')
            if isinstance(miss, str) and miss:
                print(f'          ↳ без знімка: {SHOT_MISS.get(miss) or agent_line(miss, 60)}')
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
                # локальний файл пише браузер, а не `agent_pin`: рядки якоря чистимо тут, інакше `fp.text` із переносом підробив би рамку
                anchor = agent_line((fp.get('text') or '').strip(), 50)
                path = agent_line(' > '.join(str(x) for x in (fp.get('path') or [])[-3:]), 300)
                print(f'          ↳ якір: <{agent_line(fp.get("tag") or "?", 50)}>'
                      + (f' «{anchor}»' if anchor else '')
                      + (f'  · {path}' if path else ''))
            html = _snapshot_html(p)
            sel = root_selector(html)
            if sel:
                print(f'          ↳ селектор: {agent_line(sel, 300)}')
            if html:
                print(f'          ↳ html: {agent_line(html_head(html), 300)}')
    if resolved:
        print(f'  {label}: (+ {resolved} вирішених в історії)')
    return len(openp)


def resolve_task(wanted):
    """(id, задача) названої `--task` (None — поточна) або None, коли такої немає:
    тоді `error: …` уже надруковано в stderr і виходити з кодом 2.

    Невідома назва НЕ відкочується на поточну: це і була вада (fb-07102026-e627c2) —
    помилка в id тихо читала б і закривала піни чужої задачі.

    Названа задача шукається в УСІХ просторах (`task_anywhere`), і простір, де вона є,
    лишається зафіксованим на потоці до кінця команди (її скине `main()`)."""
    try:
        # `load_tasks` — мій імпорт, а не `serve`-івський: тести-пастки патчать його тут.
        return task_anywhere(wanted, load=load_tasks)
    except TaskNotHere:
        # Задача Є в реєстрі, але теки на цій машині нема: «порожній інбокс» тут
        # був би брехнею, а відкат на поточну — тією самою вадою.
        print(f"error: задачі '{wanted}' немає на цій машині "
              '(є в реєстрі, теки нема)', file=sys.stderr)
        return None
    except UnknownTask:
        print(f'error: немає задачі {wanted!r} у tasks.json', file=sys.stderr)
        return None
    except NoTask as e:
        # «Створи простір» тут брехало б, коли задачі є в інших просторах (див. `no_task_message`).
        print(f'error: {spaces.no_task_message(e)}', file=sys.stderr)
        return None
    except AmbiguousTask:
        print(f'error: задача {wanted!r} є в кількох просторах — перейменуй одну з них '
              '(або онови id в tasks.json простору)', file=sys.stderr)
        return None
    except (SpaceUnavailable, spaces.SpacesError) as e:
        print(f'error: простір недоступний — {e}', file=sys.stderr)
        return None


def _say(e):
    """Текст винятку для ВИВОДУ: одним рядком, без керівних і невидимих символів, ≤ 500. Текст помилки модуля кидає код
    модуля (`ProjectComments` уже чистить його центрально — тут друга лінія), а ESC/OSC у терміналі агента міняють екран,
    сурогат валить `print` (`UnicodeEncodeError`), невидимий символ ховає інструкцію від людини, яку побачить агент."""
    return agent_line(str(e), 500)


def project_comments():
    """Хто веде проєктні коментарі простору ЗАДАЧІ, яку щойно знайшов `resolve_task`.

    Простір — ЯВНО: `resolve_task` (`task_anywhere`) зафіксував на потоці простір, де лежить задача (названа `--task` — у
    БУДЬ-ЯКОМУ просторі, а не лише поточному), і `spaces.active_space()` віддає саме його запис. Далі рішення
    приймає постачальник ролі `comments` цього запису (`ProjectComments`), а не прапорця `integrations`: простір із
    модулем коментарів, але без інтеграцій, має командні коментарі, а простір ЛІГА з модулем, що не завантажився, — не
    має права йти в спільний Supabase."""
    return ProjectComments(spaces.active_space())


def cmd_list(where=False, task_id=None, show_all=False):
    got = resolve_task(task_id)
    if got is None:
        return 2
    tid, task = got
    local = read_local(task)
    team_off = False
    source = 'Supabase'
    try:
        pc = project_comments()
        source = pc.label
        proj, proj_err = pc.pins(task, tid), None
    except spaces.RoleOff:
        # Простір без інтеграцій і без модуля коментарів: командних коментарів у ньому нема, а не «не дістати».
        proj, proj_err, team_off = [], None, True
    except Exception as e:  # noqa: BLE001 — зокрема `ModuleError`: лише локальні піни + повідомлення, не Supabase
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
    print(f'\n-- ПРОЄКТ (колеги + історія, {source}) --' if show_all
          else f'\n-- ПРОЄКТ · доручені Claude ({source}) --')
    if team_off:
        print('  командних коментарів у цьому просторі нема')
        ext = 0
    elif proj_err is None:
        # Б2.3: типово — лише доручені Claude командні (`for_agent`); `--all` — усі, байт-у-байт як до 0.27.0.
        mine = proj if show_all else [p for p in proj if for_agent(p, 'project')]
        print(_newest_line(mine))
        if isinstance(proj, ModulePins) and proj.note():
            print(f'  ⚠ {proj.note()}')
        ext = show_pins(mine, 'проєкт', 'P', wmap)
        if not show_all:
            hidden = len([p for p in proj if p.get('status') != 'resolved' and not for_agent(p, 'project')])
            if hidden:
                flag = f' --task {shlex.quote(tid)}' if task_id is not None else ''
                print(f'  ще {hidden} відкритих командних без доручення Claude — усі: python3 bin/inbox.py{flag} --all')
    else:
        print(f'  проєкт: (не дістати: {_say(proj_err)})')
        ext = 0
    if not ext and not team_off:
        print('  (немає відкритих)')
    print(f'\nРазом до відпрацювання: {total} локальних + {ext} проєктних')
    if total + ext:
        # Підказку копіюють дослівно: без `--task` вона закрила б пін ПОТОЧНОЇ задачі.
        flag = f' --task {shlex.quote(tid)}' if task_id is not None else ''
        print(f'Закрити: python3 bin/inbox.py{flag} resolve <id> --reason "що зроблено"')
        print(f'Відповісти в гілці: python3 bin/inbox.py{flag} reply <id> --text "питання чи примітка"')
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
    if len(prefix) < MIN_PREFIX:
        # Короткий збіг — лише ПОВНИЙ id (його пропускає `cmd_resolve` для просторів із модулем коментарів: id модуля
        # може бути коротшим за `MIN_PREFIX`). Префіксом із двох символів не закривають.
        return [p for p in pins if (p.get('id') or '').lower() == prefix]
    return [p for p in pins if (p.get('id') or '').lower().startswith(prefix)]


def _is_open(p):
    return p.get('status') != 'resolved'


def _cand(p):
    return f'{agent_line(p.get("id") or "", 8)} «{agent_line((p.get("text") or "").strip(), 40)}»'


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
    except spaces.RoleOff:
        project = []        # простір без інтеграцій: проєктних пінів нема, шукаємо лише серед локальних
    except Exception as e:  # noqa: BLE001
        # ⛔ Не «не знайдено»: ми не знаємо, чи він там є.
        closed = [p for p in _match(local, prefix) if not _is_open(p)]
        if closed:
            return 'closed', closed
        return None, f'локально немає, а проєкт недоступний ({_say(e)})'
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


def cmd_resolve(a, rp=None):
    """`resolve`: закрити пін(и) з причиною.

    Навіщо: CLI для цього не було, і сесії щоразу писали ручні скрипти або
    правили `.dc-local-comments.json` руками (fb-22092026-6aed32).

    Уже закритий пін — «сказати й пропустити», і код виходу він НЕ псує:
    повторний прогін тієї самої команди після часткового збою мусить пройти,
    а не впасти на пінах, які вже в потрібному стані. Ненульовий код — рівно
    коли хоч один пін лишився відкритим: не знайдено, неоднозначно, мережа.

    Номер ітерації (`--it`, типово — робоча) потрібен локальним пінам (`resolvedV`) і проєктним пінам ЛІГИ (`resolved_v`
    через вбудований `supabase-comments`, `ProjectComments.takes_iteration`). Власний модуль простору його не отримує
    (контракт `resolve` ролі його не має). Префікс коротший за `MIN_PREFIX` — лише у просторі з модулем і лише як ПОВНИЙ id.
    """
    got = resolve_task(a.task)
    if got is None:
        return 2
    tid, task = got
    n = a.it if a.it is not None else default_iteration(task)
    short = [p for p in a.prefixes if len(p.strip()) < MIN_PREFIX]
    module_space = None
    if n is None or short:
        try:
            # ⛔ «Не ЛІГА»: `kind == 'module'` І схема не comment-layer — мігрована ЛІГА (4d-3b) теж `kind == 'module'`, але
            # поводиться як у 0.17: без цього ліміт `MIN_PREFIX` мовчки зник би.
            pc = project_comments()
            module_space = pc.kind == 'module' and not pc.legacy_scheme
        except Exception:  # noqa: BLE001 — рішення «звідки» не вдалось: поводимось як для ЛІГА
            module_space = False
    if short and not module_space:
        msg = f'префікс коротший за {MIN_PREFIX} символів: {", ".join(short)}'
        if rp is not None:
            rp.error(msg)
        print(f'error: {msg}', file=sys.stderr)
        return 2
    if n is None and not module_space:
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
                cache['pc'] = project_comments()
                cache['pins'] = cache['pc'].pins(task, tid)
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

    if n is None and local_ids:
        # Лише простір із модулем дійшов сюди без номера ітерації: пінам модуля він не потрібен, локальним — так.
        for p in local_ids:
            print(f'✗ {p["id"][:8]}: не вдалося визначити номер робочої ітерації для локального піна — задай --it N')
            failed += 1
        local_ids = []

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
    pc = cache.get('pc')            # є, коли хоч один проєктний пін знайдено: його знайшов `project_loader`
    for p in project_pins:
        # Номер ітерації — лише коли його приймає модуль (`takes_iteration`: ЛІГА й вбудований `supabase-comments`):
        # контракт `resolve` власного модуля його не має, і «Іт.N» про такий пін було б неправдою.
        it_tag = f' Іт.{n}' if pc.takes_iteration and n is not None else ''
        if a.dry_run:
            print(f'[dry-run] {pc.label}: resolve {pc.channel(task, tid)} {p["id"]}{it_tag} '
                  f'{json.dumps(reason, ensure_ascii=False)}')
            continue
        try:
            pc.resolve(task, tid, p['id'], reason, iteration=n)
            print(f'✓ {p["id"][:8]} закрито (проєкт{"," + it_tag if it_tag else ""}): «{reason}»')
        except Exception as e:  # noqa: BLE001 — кожен пін звітує сам за себе
            print(f'✗ {p["id"][:8]}: {pc.label} не прийняв ({_say(e)})')
            failed += 1
    if a.dry_run:
        print('[dry-run] нічого не записано')
    return 1 if failed else 0


# ---------- reply ----------

def write_local_reply(path, pin_id, text, now):
    """Дописати відповідь агента під ВІДКРИТИЙ локальний пін: `{id: uuid4, author: 'AI', text, ts, agent: true}`.

    Файл перечитується ТУТ, безпосередньо перед записом (як у `write_local_resolved`): пошук цілі був раніше, а вкладка канваса
    могла за цей час дописати пін чи відповідь. Запис — `atomic_write_json` (`indent=1`, як у `serve._local_comments_post`).
    Вкладка зливає тристоронньо (`mergeReplies` у `local-adapter.js`), тож додана тут відповідь не губиться.

    `now` — `datetime`. → ('ok', id відповіді) · ('closed', None) — закрили між пошуком і записом · ('missing', None) — піна вже нема."""
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    for p in data if isinstance(data, list) else ():
        if not (isinstance(p, dict) and p.get('id') == pin_id):
            continue
        if not _is_open(p):
            return 'closed', None
        rid = str(uuid.uuid4())
        if not isinstance(p.get('replies'), list):
            p['replies'] = []
        p['replies'].append({'id': rid, 'author': 'AI', 'text': text, 'ts': now.strftime(TS_FORMAT), 'agent': True})
        atomic_write_json(path, data, indent=1)
        return 'ok', rid
    return 'missing', None


def cmd_reply(a):
    """`reply ID --text "…"`: відповісти в гілці під пінем від імені `AI`.

    Лише ВІДКРИТИЙ пін. Командний — лише ДОРУЧЕНИЙ Claude (`for_agent`): відповідь у чужому піні колег бачать усі, тож агент не
    встряє туди, куди його не кликали. Модуль без `reply` — відмова, а не тиха втрата. Текст (непорожній, ≤ `REPLY_MAX`) уже
    перевірено в `_main`. Код виходу — 0 лише коли відповідь додано (чи `--dry-run` її прийняв би)."""
    got = resolve_task(a.task)
    if got is None:
        return 2
    tid, task = got
    text = a.text.strip()
    path = _local_path(task)
    local = read_local(task)
    local = [p for p in local if isinstance(p, dict)] if isinstance(local, list) else []
    cache = {}

    def project_loader():
        if 'pins' not in cache:
            try:
                cache['pc'] = project_comments()
                cache['pins'] = cache['pc'].pins(task, tid)
            except Exception as e:  # noqa: BLE001
                cache['pins'] = e
        if isinstance(cache['pins'], Exception):
            raise cache['pins']
        return cache['pins']

    prefix = a.prefix.strip().lower()
    kind, found = find_target(prefix, local, project_loader)
    if kind is None:
        print(f'✗ {a.prefix}: {found}')
        return 1
    if kind == 'closed':
        for p in found:
            print(f'✗ {(p.get("id") or "")[:8]}: пін закрито — відповідати можна лише на відкритий')
        return 1
    short = found['id'][:8]
    if kind == 'local':
        if a.dry_run:
            print(f'[dry-run] {path}: {short} ← відповідь AI {json.dumps(text, ensure_ascii=False)}')
            print('[dry-run] нічого не записано')
            return 0
        try:
            state, _rid = write_local_reply(path, found['id'], text, datetime.now())
        except (OSError, ValueError) as e:
            print(f'✗ локальний файл не переписано ({_say(e)})')
            return 1
        if state == 'closed':
            print(f'✗ {short}: пін закрито, поки йшов пошук — відповідати можна лише на відкритий')
            return 1
        if state != 'ok':
            print(f'✗ {short}: піна вже нема в локальному файлі')
            return 1
        print(f'✓ {short} відповідь додано (локальний)')
        return 0
    if not for_agent(found, 'project'):
        print(f'✗ {short}: пін не доручено AI — відповідати можна лише в дорученому')
        return 1
    pc = cache['pc']
    if a.dry_run:
        if pc.prov is None or pc.prov.fn('reply') is None:
            print(f'✗ {short}: модуль коментарів не підтримує відповідей')
            return 1
        print(f'[dry-run] {pc.label}: reply {pc.channel(task, tid)} {found["id"]} {json.dumps(text, ensure_ascii=False)}')
        print('[dry-run] нічого не записано')
        return 0
    try:
        done = pc.reply(task, tid, found['id'], text)
    except Exception as e:  # noqa: BLE001
        print(f'✗ {short}: {pc.label} не прийняв ({_say(e)})')
        return 1
    if done is None:
        print(f'✗ {short}: модуль коментарів не підтримує відповідей')
        return 1
    print(f'✓ {short} відповідь додано (проєкт)')
    return 0


# ---------- аргументи ----------

EPILOG = """\
Закрити пін (id — перші символи з виводу, «[3f2a9c1b · автор]»):
  python3 bin/inbox.py resolve 3f2a9c1b --reason "кнопку перенесено в шапку"
  python3 bin/inbox.py resolve 3f2a9c 7d41e0 --reason "..." --it 4 --dry-run
Відповісти в гілці під пінем (питання чи примітка; лише на відкритий, командний — лише доручений Claude):
  python3 bin/inbox.py reply 3f2a9c1b --text "це про кнопку в шапці чи в підвалі?"
  python3 bin/inbox.py reply 3f2a9c1b --text "..." --dry-run
Паралельні сесії: `current` один на машину, тож називай свою задачу — `--task` стоїть
ПЕРЕД підкомандою (після неї — помилка):
  python3 bin/inbox.py --task bf360
  python3 bin/inbox.py --task bf360 resolve 3f2a9c1b --reason "..."
Подробиці: python3 bin/inbox.py resolve -h · python3 bin/inbox.py reply -h
"""


def build_parser():
    ap = argparse.ArgumentParser(
        prog='inbox.py',
        description='Коментарі-піни поточної (або названої --task) задачі: '
                    'локальні (мені) + проєктні (Supabase ЛІГА чи модуль коментарів). Без аргументів — '
                    'перелік відкритих.',
        epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--task', metavar='ID',
                    help='задача з tasks.json замість поточної — для паралельних сесій '
                         '(перед підкомандою); невідомий id чи задача без теки на цій '
                         'машині — помилка, а не поточна задача')
    ap.add_argument('--where', action='store_true',
                    help='для кожного відкритого піна — віджет і скільки таких самих '
                         'елементів на сторінці (браузер; потрібен запущений канвас)')
    ap.add_argument('--all', action='store_true',
                    help='усі командні коментарі, а не лише доручені Claude (як до 0.27.0)')
    sub = ap.add_subparsers(dest='cmd', metavar='{resolve,reply}')
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
                    help=f'префікс id піна, не коротший за {MIN_PREFIX} символів (у просторі з модулем коментарів '
                         'коротший id — лише повністю)')
    rp.add_argument('--reason', required=True,
                    help='що зроблено — обовʼязково: без причини comment-layer '
                         'показує «resolved manually», і дизайнер не знає, що змінилось')
    rp.add_argument('--it', type=int, metavar='N',
                    help='номер ітерації, в якій закрито (типово — робоча: остання своя); для пінів модуля '
                         'коментарів не потрібен і ігнорується (контракт модуля його не має)')
    rp.add_argument('--dry-run', action='store_true',
                    help='надрукувати, що було б записано, нічого не міняючи')
    yp = sub.add_parser(
        'reply', help='відповісти в гілці під пінем',
        description='Дописати відповідь від імені AI під ВІДКРИТИМ пінем поточної (або названої --task) задачі: питання, якщо '
                    'зміст коментаря неоднозначний, чи примітка. Локальний пін — у локальний файл; командний — лише доручений '
                    'Claude, і відповідь бачать колеги.',
        epilog='Приклад: python3 bin/inbox.py reply 3f2a9c1b --text "це про кнопку в шапці?"',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    yp.add_argument('prefix', metavar='ID', help=f'префікс id піна, не коротший за {MIN_PREFIX} символів')
    yp.add_argument('--text', required=True, help=f'текст відповіді (непорожній, до {REPLY_MAX} символів); '
                                                  'текст, що починається з «-», — як --text="-..."')
    yp.add_argument('--dry-run', action='store_true', help='надрукувати, що було б записано, нічого не міняючи')
    ap.set_defaults(reply_parser=yp)
    return ap, rp


def main(argv=None):
    # Простір, який `resolve_task` фіксує на потоці, не сміє пережити команду (`main()` кличуть
    # і в процесі — тести, інші скрипти).
    try:
        return _main(argv)
    finally:
        spaces.clear_request_space()


def _main(argv):
    ap, rp = build_parser()
    a = ap.parse_args(argv)
    if a.cmd == 'resolve':
        if not a.reason.strip():
            rp.error('--reason порожній: напиши, що зроблено')
        if a.it is not None and a.it < 1:
            rp.error('--it: номер ітерації — ціле від 1')
        # Короткий префікс відхиляє `cmd_resolve` — після того, як він знайшов простір задачі: лише в просторі з модулем
        # коментарів повний id коротший за `MIN_PREFIX` законний.
        return cmd_resolve(a, rp)
    if a.cmd == 'reply':
        yp = a.reply_parser
        if not a.text.strip():
            yp.error('--text порожній: напиши відповідь')
        if len(a.text.strip()) > REPLY_MAX:
            yp.error(f'--text задовгий: {len(a.text.strip())} знаків, межа {REPLY_MAX}')
        return cmd_reply(a)
    return cmd_list(where=a.where, task_id=a.task, show_all=a.all)


if __name__ == '__main__':
    sys.exit(main())
