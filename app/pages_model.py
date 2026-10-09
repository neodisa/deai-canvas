"""Чиста модель сторінок ітерації design-canvas (без HTTP/мережі — тестується юнітами).

Дерево довільної глибини (запобіжник MAX_DEPTH лише від патологічних даних):
  [{ id, name, kind, published?, isGroup?, children?:[…] }]
`kind` ∈ folder | page | state. Відсутній `kind` виводиться з положення
(`kind_of`) рівно так, як панель показувала до 30.09.2026: isGroup → тека,
дитина сторінки → стан, решта → сторінка.

Кожна сторінка/стан = тека `<id>/` з `index.html` у теці ітерації — ПЛАСКО,
незалежно від глибини: перенос у дереві міняє лише pages.json. Тека (`folder`)
файлів не має.
Назад-сумісність: нема pages.json, але є index.html у корені → одна неявна 'main'.

Правила дерева мають JS-близнюка `app/tree-model.js`; обидва ганяють
`tests/fixtures/tree-rules.json`.
"""
import contextlib
import copy
import fcntl
import hashlib
import html
import json
import os
import re
import shutil
import threading
import time

# Спільний лист писарів стану: той самий атомарний запис і ТОЙ САМИЙ лок, що в
# serve. Імпортувати serve звідси не можна (цикл), а окремий лок у цьому модулі
# не бачив би serve-івського — і два одночасні /api/page-add дали б .bak на два
# кроки назад.
from atomic_io import WRITE_LOCK, atomic_write_json

IMPLICIT_ID = 'main'
MAX_DEPTH = 32
KINDS = ('folder', 'page', 'state')

# Правило id — ОДНЕ на validate, передперевірку операцій і remove_dirs: id стає
# іменем теки ітерації, яку потім rmtree. fullmatch, а не `^…$`: `$` збігається
# перед завершальним `\n`, тож id «abc\n» проходив би.
_ID_RE = re.compile(r'[\w-]+')

# Скільки pages_lock чекає чужого писаря, перш ніж відмовити 'busy'. Константа
# модуля (а не літерал усередині), щоб тест міг притиснути її до соток секунди.
LOCK_TIMEOUT = 10.0


class TreeError(ValueError):
    """Порушення правил дерева з машинним кодом для клієнта (`code`).

    Нащадок ValueError свідомо: наявні `except ValueError` у serve ловлять і
    його, а новий код читає `code`, щоб панель показала причину своєю мовою,
    а не англійський текст сервера."""

    def __init__(self, code, message=''):
        super().__init__(message or code)
        self.code = code


def kind_of(node, parent_kind=None):
    """Тип вузла: явний `kind`, інакше вивід із положення (сумісність).

    Невалідний `kind` тут не падає — відмовляє `validate`; обхід мусить
    переживати сміття, щоб панель могла показати файл, який треба лагодити."""
    k = node.get('kind')
    if k in KINDS:
        return k
    if node.get('isGroup'):
        return 'folder'
    return 'state' if parent_kind == 'page' else 'page'


_SLUG_RE = re.compile(r'[^a-z0-9]+')
_TRANSLIT = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'h', 'ґ': 'g', 'д': 'd', 'е': 'e',
    'є': 'ie', 'ж': 'zh', 'з': 'z', 'и': 'y', 'і': 'i', 'ї': 'i', 'й': 'i',
    'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r',
    'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch',
    'ш': 'sh', 'щ': 'shch', 'ь': '', 'ю': 'iu', 'я': 'ia',
    'ё': 'e', 'ъ': '', 'ы': 'y', 'э': 'e',
}


def _translit(s):
    return ''.join(_TRANSLIT.get(ch, ch) for ch in s.lower())


def pages_path(iter_dir):
    return os.path.join(iter_dir, 'pages.json')


def _read_raw(iter_dir):
    """Байти pages.json або None. Один читач і для дерева, і для rev: mutate
    бере обидва з ОДНОГО читання, тож rev не розходиться з тим, що змінено."""
    try:
        with open(pages_path(iter_dir), 'rb') as fh:
            return fh.read()
    except FileNotFoundError:
        return None


def _rev_of(raw):
    return '' if raw is None else hashlib.sha1(raw).hexdigest()[:16]


def _tree_from_raw(iter_dir, raw):
    """Дерево з прочитаних байтів; без файла — як read_pages (неявна main).

    Файл, який не розбирається (не JSON, не UTF-8, не обʼєкт, `pages` не список),
    — `TreeError('corrupt')`: голий JSONDecodeError у обробниках сторінок рвав
    зʼєднання без відповіді, а з кодом панель може сказати, що саме зламано.
    Вузли всередині списку тут НЕ перевіряємо: це справа `_precheck`/`validate`."""
    if raw is not None:
        try:
            data = json.loads(raw.decode('utf-8'))
        except (ValueError, RecursionError):      # JSON- і UTF-8-помилки — ValueError
            raise TreeError('corrupt', 'pages.json is not valid JSON') from None
        if not isinstance(data, dict):
            raise TreeError('corrupt', 'pages.json is not an object')
        pages = data.get('pages', [])
        if not isinstance(pages, list):
            raise TreeError('corrupt', 'pages.json "pages" is not a list')
        _check_shape(pages)
        return pages
    if os.path.isfile(os.path.join(iter_dir, 'index.html')):
        return [{'id': IMPLICIT_ID, 'name': 'Головна', 'published': True}]
    return []


def _check_shape(pages):
    """Лише форма: кожен вузол — обʼєкт, `children` — список (чи порожнє/null).

    Правила (id, назви, типи) — справа `validate`/`_precheck`; тут тільки те, без
    чого сам обхід (`flatten`, `find_page`) падає голим AttributeError/TypeError
    ще до будь-якої перевірки. Читач віддає `corrupt` — панель скаже, що файл
    треба полагодити, а не обірве зʼєднання. Ітеративно: глибину не обмежуємо."""
    stack = [pages]
    while stack:
        for pg in stack.pop():
            if not isinstance(pg, dict):
                raise TreeError('corrupt', 'pages.json has a node that is not an object')
            stack.append(_children_list(pg))


def read_pages(iter_dir):
    """Дерево сторінок. Порожній список, якщо нема ні pages.json, ні кореневого index.html."""
    return _tree_from_raw(iter_dir, _read_raw(iter_dir))


def read_pages_rev(iter_dir):
    """`(дерево, rev)` з ОДНОГО читання pages.json — БЕЗ лока. Для GET.

    ⛔ Лока тут немає свідомо. `pages_lock` створює `.pages.lock`, а це піднімає
    mtime теки ітерації — за ним автосинк вибирає робочу ітерацію, і простий
    перегляд тижневої ітерації зробив би її «свіжою». Він же падає на теці «лише
    для читання» і змушує читача чекати писаря (чи rmtree). Лок читачу й не
    потрібен: `atomic_write_json` підміняє файл цілком, тож одне читання — це
    узгоджений знімок, а дерево з rev мусять бути саме з одних і тих самих байтів
    (два окремі читання лишили б між собою вікно для чужого запису)."""
    raw = _read_raw(iter_dir)
    return _tree_from_raw(iter_dir, raw), _rev_of(raw)


def write_pages(iter_dir, pages):
    """Перевірити, матеріалізувати kind і записати pages.json (.bak — крок назад).

    ⚠️ `pages_lock` тут НЕ береться: читання-зміну-запис має огортати викликач
    (або йти через `mutate`). Тут лише WRITE_LOCK, який склеює `.bak` із записом;
    від втраченої правки (читання поза локом) він не рятує."""
    validate(pages)
    materialize(pages)
    p = pages_path(iter_dir)
    # Лок бере САМЕ ця функція, а не її викликачі: `add_page`/`delete_page`
    # кличуться з обробників HTTP у потоках ThreadingHTTPServer, і два
    # одночасні /api/page-add інакше зняли б .bak з однієї версії — рівно той
    # дефект, який для iterations.json уже закритий. Той самий лок, що в serve:
    # окремий тут одне одного б не бачив.
    with WRITE_LOCK:
        if os.path.isfile(p):
            shutil.copy2(p, p + '.bak')
        atomic_write_json(p, {'pages': pages})


def materialize(pages, _parent_kind=None):
    """Явний `kind` на кожному вузлі — рівно той, що показував вивід.

    Кличеться ПІСЛЯ validate: невалідний kind інакше тихо перетворився б на
    виведений. Для тек лишаємо `isGroup: true` — колега на старій версії
    канваса інакше спробував би відкрити теку як сторінку."""
    for pg in pages:
        k = kind_of(pg, _parent_kind)
        pg['kind'] = k
        if k == 'folder':
            pg['isGroup'] = True
        else:
            pg.pop('isGroup', None)
        materialize(pg.get('children') or [], k)
    return pages


def pages_rev(iter_dir):
    """Відбиток pages.json, який бачила панель; '' — файла немає (неявна main)."""
    return _rev_of(_read_raw(iter_dir))


# Які теки ітерацій цей ПОТІК уже тримає під pages_lock (realpath).
_held = threading.local()


@contextlib.contextmanager
def pages_lock(iter_dir):
    """Міжпроцесний лок читання-зміни-запису pages.json.

    `WRITE_LOCK` бачать лише потоки сервера, а `bin/pages.py` — окремий процес.
    `flock` конфліктує й між двома відкриттями в ОДНОМУ процесі, тож серіалізує
    і потоки сервера. Файл — dot-файл у теці ітерації: експорт колегам
    (`_is_tool_junk`) і штамп зʼємки (`shots-stamp.mjs`) dot-файли пропускають,
    а `.gitignore` теки задачі (`TASK_IGNORE`) його не комітить.

    Теку ітерації НЕ створюємо: лок на неіснуючу ітерацію лишив би по собі
    порожню теку-привид, яку потім хтось прийняв би за задачу → `not-found`.

    Не реентерабельний: другий захват тієї ж теки в тому ж потоці дедлокнув би
    (другий open — інший file description), тож замість цього RuntimeError.
    Чекання обмежене LOCK_TIMEOUT: зависла чужа зміна дає 'busy', а не вічно
    висячий запит."""
    if not os.path.isdir(iter_dir):
        raise TreeError('not-found', 'iteration not found')
    key = os.path.realpath(iter_dir)
    held = getattr(_held, 'dirs', None)
    if held is None:
        held = _held.dirs = set()
    if key in held:
        raise RuntimeError('pages_lock is not reentrant')
    with open(os.path.join(iter_dir, '.pages.lock'), 'a') as fh:
        deadline = time.monotonic() + LOCK_TIMEOUT
        while True:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TreeError('busy', 'pages.json is locked by another writer')
                time.sleep(0.01)
        held.add(key)
        try:
            yield
        finally:
            held.discard(key)
            fcntl.flock(fh, fcntl.LOCK_UN)


def mutate(iter_dir, change, rev=None, *, after=None, with_rev=False):
    """Прочитати → звірити rev → change(pages) → записати, усе під локом.

    `change` отримує КОПІЮ дерева й повертає `(нове_дерево, extra)`; `extra`
    повертається викликачу. Нічого не змінилось → файл не пишемо (кожен запис
    знімає .bak, і порожній клік затер би останню справжню копію).

    rev і дерево виводяться з ОДНОГО читання байтів pages.json під локом.
    Файл, що не розбирається, відмовляє `corrupt` РАНІШЕ за `stale`: застарілий
    rev на битому файлі — не причина, а наслідок.
    `after(extra)` — необовʼязковий хук, що йде під ТИМ САМИМ локом одразу після
    запису (і лише якщо запис був): видалення тек сторінок тут не дає
    паралельному додаванню сторінки з тим самим slug втратити щойно створену
    теку. `with_rev=True` → `(extra, rev_after, changed)`: rev_after знято під
    локом (для no-op — rev файла, що не змінився), `changed` — чи був запис
    (викликач, що комітить у git, пропускає коміт, коли нічого не записано);
    за замовчуванням повертається лише `extra`.

    ⚠️ `after` НЕ має кидати винятків: коли він іде, дерево вже записано, тож
    виняток лишив би файл зміненим, а викликача — з відмовою. Тому `remove_dirs`
    не кидає, а повертає список нестертих (це контракт), і хук має так само
    звітувати, а не падати."""
    with pages_lock(iter_dir):
        raw = _read_raw(iter_dir)
        pages = _tree_from_raw(iter_dir, raw)          # corrupt — раніше за stale
        if rev is not None and rev != _rev_of(raw):
            raise TreeError('stale', 'pages.json changed since it was read')
        before = json.dumps(pages, sort_keys=True)
        new, extra = change(copy.deepcopy(pages))
        changed = json.dumps(new, sort_keys=True) != before
        if changed:
            write_pages(iter_dir, new)
            if after is not None:
                after(extra)
        if with_rev:
            return extra, pages_rev(iter_dir), changed
        return extra


def page_rel(page):
    """Відносний шлях теки сторінки в теці ітерації ('' для неявної main)."""
    return '' if page.get('id') == IMPLICIT_ID else page['id']


def flatten(pages, _depth=0, _parent=None, _parent_kind=None):
    """[{'page', 'parent', 'depth', 'kind'}] обходом у порядку дерева, усі рівні.

    Сплющення ПІДДЕРЕВА (`flatten([node])`) губить тип батька: легасі-вузол без
    kind, що був станом, вийде як 'page'. Коли тип важливий — сплющуй усе дерево
    або передай `_parent_kind` явно."""
    out = []
    for pg in pages:
        k = kind_of(pg, _parent_kind)
        out.append({'page': pg, 'parent': _parent, 'depth': _depth, 'kind': k})
        out.extend(flatten(pg.get('children') or [], _depth + 1, pg.get('id'), k))
    return out


def openable_pages(pages):
    """Сторінки й стани, які реально відкриваються (теки — ні)."""
    return [f['page'] for f in flatten(pages) if f['kind'] != 'folder']


def preview_flat(pages):
    """Відкривані вузли, що їдуть у превʼю: вузол і ВСІ предки не
    `published: false` (рішення власника 30.09.2026 — приховування на
    піддерево). Порядок — порядок дерева; той самий формат, що `flatten`."""
    return [f for f in _visible(pages) if f['kind'] != 'folder']


def preview_outline(pages):
    """Усе видиме дерево для панелі превʼю, З ТЕКАМИ — але лише з тими, у
    піддереві яких є що відкрити: порожня тека в превʼю була б рядком, який
    нікуди не веде."""
    vis = _visible(pages)
    keep = []
    for i, f in enumerate(vis):
        if f['kind'] != 'folder':
            keep.append(f)
            continue
        # є відкриваний нащадок: наступні рядки глибші за теку, до першого не-глибшого
        # (індекс, а не зріз `vis[i + 1:]` — копія хвоста на кожну теку)
        for j in range(i + 1, len(vis)):
            g = vis[j]
            if g['depth'] <= f['depth']:
                break
            if g['kind'] != 'folder':
                keep.append(f)
                break
    return keep


def _visible(pages, _depth=0, _parent=None, _parent_kind=None):
    """`flatten` без схованих піддерев: `published: false` на вузлі відсікає його
    разом з усіма нащадками (явне `true` на нащадку цього не скасовує).

    kind рахується тут же, по ходу обходу ВСЬОГО дерева: схований вузол пропускаємо
    цілком, а видимі діти дістають тип батька від видимого батька — той самий, що
    дав би `flatten`."""
    out = []
    for pg in pages:
        if pg.get('published') is False:
            continue
        k = kind_of(pg, _parent_kind)
        out.append({'page': pg, 'parent': _parent, 'depth': _depth, 'kind': k})
        out.extend(_visible(pg.get('children') or [], _depth + 1, pg.get('id'), k))
    return out


def find_page(pages, page_id):
    """(page, siblings_list) або (None, None). `siblings_list` — САМ список
    у дереві (не копія): викликачі вставляють/виймають у нього на місці."""
    for pg in pages:
        if pg.get('id') == page_id:
            return pg, pages
        kids = pg.get('children')
        if kids:
            found = find_page(kids, page_id)
            if found[0] is not None:
                return found
    return None, None


def path_of(pages, page_id):
    """[корінь, …, вузол] або [] — для власника стану й заголовків-шляхів."""
    for pg in pages:
        if pg.get('id') == page_id:
            return [pg]
        sub = path_of(pg.get('children') or [], page_id)
        if sub:
            return [pg] + sub
    return []


# Імена, які в теці ітерації вже щось означають: сторінка з таким id стала б
# текою на диску поверх них. Лише для НОВИХ id — у `validate` цього немає
# свідомо, інакше наявні дерева з такими id стали б нечитабельними.
RESERVED_IDS = frozenset({
    IMPLICIT_ID,                  # page_rel('main') == '' → корінь ітерації, а не тека
    'assets', 'icons', 'fonts',   # спільні файли ітерації (serve.copy_iteration_shared)
    'shots',                      # склад кадрів (copy_iteration_shared, /api/shots)
    'publish', 'iterations',      # serve.SKIP: copy_mockup/_mockup_files їх відсіюють
})


def _slug(name, taken):
    base = _SLUG_RE.sub('-', _translit(name)).strip('-') or 'page'
    taken = set(taken) | RESERVED_IDS
    slug, i = base, 2
    while slug in taken:
        slug = f'{base}-{i}'
        i += 1
    return slug


def _all_ids(pages):
    return {f['page']['id'] for f in flatten(pages)}


def add_page(iter_dir, pages, name, parent_id=None, kind='page', index=None):
    """Створює теку <id>/index.html + вписує в дерево. Повертає (pages, new_page).

    `kind` — 'page' або 'state' (теку створює op_add_folder: у неї немає файлів).
    `index` — позиція серед дітей батька (None — у кінець; число обрізається до
    меж): так CLI ставить вузол «після X» одним записом, без проміжного стану."""
    # не-рядок (`5`, список) — теж порожнє імʼя: `.strip()` на ньому падав
    # AttributeError, і клієнт діставав обрив зʼєднання замість JSON-відмови
    name = name.strip() if isinstance(name, str) else ''
    if not name:
        raise TreeError('empty-name', 'empty page name')
    if kind not in ('page', 'state'):
        raise TreeError('bad-kind', f'add_page cannot create {kind!r}')
    if index is not None and (isinstance(index, bool) or not isinstance(index, int)):
        raise TreeError('bad-index', 'index must be an integer or None')
    # Теки, що вже лежать на диску (спільні `img/`, чужі файли), теж зайняті:
    # slug, який збігся б із ними, змішав би сторінку зі спільним вмістом.
    on_disk = set(os.listdir(iter_dir)) if os.path.isdir(iter_dir) else set()
    pid = _slug(name, _all_ids(pages) | on_disk)
    page = {'id': pid, 'name': name, 'kind': kind, 'published': True}
    if parent_id:
        parent, _ = find_page(pages, parent_id)
        if parent is None:
            raise TreeError('not-found', 'parent not found')
        dest = parent.setdefault('children', [])
    else:
        dest = pages
    dest.insert(len(dest) if index is None else max(0, min(index, len(dest))), page)
    try:
        validate(pages)
    except TreeError:
        # відкотити вставку: викликач тримає цей самий список
        dest.remove(page)
        raise
    pdir = os.path.join(iter_dir, pid)
    os.makedirs(pdir, exist_ok=True)
    esc = html.escape(name)
    with open(os.path.join(pdir, 'index.html'), 'w', encoding='utf-8') as f:
        f.write('<!DOCTYPE html><html lang="uk"><head><meta charset="utf-8">'
                f'<title>{esc}</title></head><body><h1>{esc}</h1>'
                '<p>Нова сторінка — почни проєктувати.</p></body></html>')
    write_pages(iter_dir, pages)
    return pages, page


def rename_page(iter_dir, pages, page_id, name):
    page, _ = find_page(pages, page_id)
    if page is None:
        raise TreeError('not-found', f'page not found: {page_id}')
    if not isinstance(name, str):       # як у add_page: `.strip()` на числі — обрив зʼєднання
        raise TreeError('empty-name', 'page name must be a string')
    page['name'] = name.strip()
    write_pages(iter_dir, pages)
    return pages


def set_published(iter_dir, pages, page_id, value):
    page, _ = find_page(pages, page_id)
    if page is None:
        raise TreeError('not-found', f'page not found: {page_id}')
    page['published'] = bool(value)
    write_pages(iter_dir, pages)
    return pages


def delete_page(iter_dir, pages, page_id):
    """Легасі-вхід (видалити з усім піддеревом). Порядок несучий: СПЕРШУ дерево,
    ПОТІМ теки — інакше відмова запису лишала стерті файли під старим pages.json."""
    new, removed = op_delete(pages, page_id, 'all')
    write_pages(iter_dir, new)
    remove_dirs(iter_dir, removed)
    pages[:] = new
    return pages


def reparent_page(iter_dir, pages, page_id, parent_id):
    """Перенести сторінку під parent (None → верхній рівень), у кінець його дітей."""
    if parent_id and parent_id == page_id:
        raise TreeError('cycle', 'cannot reparent a page under itself')
    new = op_move(pages, [page_id], parent_id or None, 10 ** 9)
    write_pages(iter_dir, new)
    pages[:] = new
    return pages


def move_page(iter_dir, pages, page_id, index):
    """Поставити сторінку на позицію `index` СЕРЕД ЇЇ СУСІДІВ (той самий батько).

    ⛔ НАВІЩО (fb-09092026-d4c51b, 09.09.2026). Порядок у панелі досі був
    ХРОНОЛОГІЄЮ роботи: у lu-home 19 дочірніх сторінок стояли так, як їх
    заводили, і найцікавіший варіант опинився останнім. Серед функцій моделі
    не було жодної, що міняє порядок, — `reparent_page` міняє лише батька й
    кладе в КІНЕЦЬ, — тож переставляли руками в `pages.json`.

    `index` — позиція ПІСЛЯ переставлення (0 — перша), обрізається до меж:
    «вище за першу» — це перша, і відмова тут була б педантизмом, а не
    захистом. Перенос до ІНШОГО батька — не ця функція (`reparent_page`):
    одна дія — одна зміна, інакше «підняти» мовчки міняло б і вкладеність.

    Нічого не змінилось → не пишемо: кожен запис знімає `.bak`, і клік на
    місці затер би останню справжню резервну копію. Порядок їде колегам разом
    із `pages.json` — синк везе теку ітерації цілком, нового нічого не треба.
    """
    page, siblings = find_page(pages, page_id)
    if page is None:
        raise ValueError('page not found')
    if isinstance(index, bool) or not isinstance(index, int):
        raise ValueError('index must be an integer')
    old = siblings.index(page)
    new = max(0, min(index, len(siblings) - 1))
    if new == old:
        return pages
    siblings.pop(old)
    siblings.insert(new, page)
    write_pages(iter_dir, pages)
    return pages


def top_ids(pages, ids):
    """Лише «верхні» з вибраних, у порядку дерева: вибрали теку й щось у ній —
    рухається тека (дитина їде з нею)."""
    want = set(ids)
    out = []
    for f in flatten(pages):
        pid = f['page'].get('id')
        if pid in want and not any(a.get('id') in want for a in path_of(pages, pid)[:-1]):
            out.append(pid)
    return out


def _children_list(pg):
    """Діти вузла як список (порожній, коли `children` нема чи порожнє/null).

    Не-список (обʼєкт, рядок, число — pages.json правили руками) → `corrupt`:
    обхід ітерував би ключі обʼєкта чи символи рядка й падав би голим
    AttributeError/TypeError (500 без коду). Код `corrupt` — той самий, що для
    файла, який не розбирається: дерево непридатне для обходу."""
    kids = pg.get('children') or []
    if not isinstance(kids, list):
        raise TreeError('corrupt', f'children of {pg.get("id")!r} is not a list')
    return kids


def _precheck(pages):
    """Вузька передперевірка входу операцій: у кожного вузла є id-рядок за
    правилом id, а явний `kind` — один із KINDS.

    Навіщо окремо від `validate`: операції працюють із деревом, яке прийшло з
    диска, і без цього вузол без id давав би голий KeyError (500), а невалідний
    kind `materialize` тихо перетворив би на виведений. Повний `validate` на вході
    не можна: він відхилив би й легасі-дерево, яке `op_set_kind` якраз мусить
    полагодити (`[p[c[d]]]` без kind — c виводиться станом із дитиною)."""
    for pg in pages:
        if (not isinstance(pg, dict) or not isinstance(pg.get('id'), str)
                or not _ID_RE.fullmatch(pg['id'])):
            raise TreeError('bad-id', f'bad id: {pg.get("id") if isinstance(pg, dict) else pg!r}')
        if 'kind' in pg and pg['kind'] not in KINDS:
            raise TreeError('bad-kind', f'bad kind: {pg["kind"]!r}')
        _precheck(_children_list(pg))


def _unreferenced(tree, rels):
    """`rels` без тих, на які ще посилається вузол `tree`.

    Дубль id (злиття гілок у git) дає два вузли на одну теку `<id>/`: операція
    прибирає один, і стерти теку означало б знищити файли того, що лишився."""
    still = {page_rel(f['page']) for f in flatten(tree)}
    return [r for r in rels if r not in still]


def _children_of(pages, parent_id):
    """Список дітей `parent_id` (None — сам корінь). `setdefault` лишає порожній
    `children: []` на батьку, якщо викликач нічого не вставить: прибирати його —
    справа викликача (див. op_move)."""
    if parent_id is None:
        return pages
    node, _ = find_page(pages, parent_id)
    if node is None:
        raise TreeError('not-found', f'parent not found: {parent_id}')
    return node.setdefault('children', [])


def op_move(pages, ids, parent, index):
    """Перенести `ids` (разом, у порядку дерева) під `parent` (None — корінь) на
    позицію `index` СЕРЕД ДІТЕЙ ПІСЛЯ виймання; індекс обрізається до меж.
    Порушення правил → TreeError, вхідне дерево не зачеплене.

    Тип вузла без `kind` виводиться з БАТЬКА (`kind_of`), тож зміна батька тихо
    перетворила б легасі-стан на сторінку. Тому тип беремо з ЦІЛОГО дерева ДО
    виймання й закріплюємо явно лише там, де батько справді міняється:
    перестановка в межах одного батька лишає вузол байт-у-байт (noop). Нащадків
    закріплювати не треба: їхній вивід залежить від типу переносимого кореня."""
    if isinstance(index, bool) or not isinstance(index, int):
        raise TreeError('bad-index', 'index must be an integer')
    _precheck(pages)
    t = copy.deepcopy(pages)
    for i in ids:
        if find_page(t, i)[0] is None:
            raise TreeError('not-found', f'page not found: {i}')
    ids = top_ids(t, ids)
    was = {f['page']['id']: (f['parent'], f['kind']) for f in flatten(t)}
    if parent is not None:
        if parent in ids or any(a.get('id') in ids for a in path_of(t, parent)):
            raise TreeError('cycle', 'cannot move a node into itself or its descendant')
        pnode, _ = find_page(t, parent)
        if pnode is None:
            raise TreeError('not-found', f'parent not found: {parent}')
        pk = next(f['kind'] for f in flatten(t) if f['page'] is pnode)
        if pk == 'state':
            raise TreeError('state-has-children', 'cannot put anything inside a state')
    moved = []
    old_parents = set()
    for i in ids:
        node, sibs = find_page(t, i)
        old_parents.add(was[i][0])
        # `'kind' not in`, а не «завжди»: явний, але невалідний kind закріплення
        # перетворило б на виведений, і validate його вже не впіймав би
        if 'kind' not in node and was[i][0] != parent:
            node['kind'] = was[i][1]
        sibs.remove(node)
        moved.append(node)
    dest = _children_of(t, parent)
    at = max(0, min(index, len(dest)))
    dest[at:at] = moved
    # Порожній `children: []` прибираємо лише на вузлах, яких торкнулась ця дія
    # (старі батьки рухомих і місце призначення). Чужий `children: []` десь
    # збоку — не наша справа: прибравши його, «порожній» перенос переписав би файл.
    for pid in old_parents | {parent}:
        if pid is None:
            continue
        n, _ = find_page(t, pid)
        if n is not None and n.get('children') == []:
            n.pop('children')
    validate(t)
    return t


def op_add_folder(pages, name, parent=None, index=None):
    """Нова тека (kind=folder, isGroup, published) у `parent` (None — корінь) на
    позиції `index` (None — у кінець; число обрізається до меж).
    Повертає (дерево, тека)."""
    if not isinstance(name, str) or not name.strip():
        raise TreeError('empty-name', 'empty folder name')
    name = name.strip()
    if index is not None and (isinstance(index, bool) or not isinstance(index, int)):
        raise TreeError('bad-index', 'index must be an integer or None')
    _precheck(pages)
    t = copy.deepcopy(pages)
    folder = {'id': _slug(name, _all_ids(t)), 'name': name, 'kind': 'folder',
              'isGroup': True, 'published': True}
    if parent is not None:
        pnode, _ = find_page(t, parent)
        if pnode is None:
            raise TreeError('not-found', f'parent not found: {parent}')
    dest = _children_of(t, parent)
    at = len(dest) if index is None else max(0, min(index, len(dest)))
    dest.insert(at, folder)
    validate(t)
    return t, folder


def op_group(pages, ids, name):
    """Загорнути сусідів у нову теку на місці першого з них.
    Повертає (дерево, тека) — тека ВЗЯТА З повернутого дерева, тобто з дітьми."""
    _precheck(pages)
    t = copy.deepcopy(pages)
    for i in ids:               # як op_move: невідомий id — відмова, а не мовчки менша група
        if find_page(t, i)[0] is None:
            raise TreeError('not-found', f'page not found: {i}')
    ids = top_ids(t, ids)
    if not ids:
        raise TreeError('not-found', 'nothing to group')
    parents = {(path_of(t, i)[-2]['id'] if len(path_of(t, i)) > 1 else None) for i in ids}
    if len(parents) != 1:
        raise TreeError('not-siblings', 'only siblings can be grouped')
    parent = parents.pop()
    dest = _children_of(t, parent)
    first = min(dest.index(find_page(t, i)[0]) for i in ids)
    t, folder = op_add_folder(t, name, parent=parent, index=first)
    out = op_move(t, ids, folder['id'], 0)
    return out, find_page(out, folder['id'])[0]


def op_unwrap(pages, node_id):
    """Прибрати вузол, його дітей поставити на його місце.
    Повертає (дерево, [теки файлів, які треба стерти])."""
    _precheck(pages)
    t = copy.deepcopy(pages)
    node, sibs = find_page(t, node_id)
    if node is None:
        raise TreeError('not-found', f'page not found: {node_id}')
    flat = flatten(t)
    kind = next(f['kind'] for f in flat if f['page'] is node)
    # Підняті діти отримують НОВОГО батька, а тип без `kind` виводиться з батька:
    # легасі-сторінка в теці, піднята до сторінки, тихо стала б станом.
    # Закріплюємо типи, порахованими ДО підняття (той самий принцип, що в op_move).
    was = {f['page']['id']: f['kind'] for f in flat}
    for ch in node.get('children') or []:
        if 'kind' not in ch:
            ch['kind'] = was[ch['id']]
    at = sibs.index(node)
    sibs[at:at + 1] = node.get('children') or []
    validate(t)
    removed = [] if kind == 'folder' or not page_rel(node) else [page_rel(node)]
    return t, _unreferenced(t, removed)


def op_ungroup(pages, node_id):
    """Розгрупувати ТЕКУ: її діти стають на її місце. Повертає нове дерево.

    Лише тека. «Розгрупувати» сторінку прибрало б її з дерева, не стерши файли, —
    тиха осиротіла тека; видалення сторінки — це `op_delete` з явним mode.
    Тип беремо з ЦІЛОГО дерева (`flatten`), тим самим `kind_of`, що й усі
    операції: явний `kind` сильніший за легасі-`isGroup`, а дитина сторінки без
    kind — стан. Сирий прапорець `isGroup` на вузлі помилково пропустив би
    вручну зіпсований `kind: page` + `isGroup: true`, і `op_unwrap`, бачачи
    сторінку, не повернув би її теку на стирання.
    not-found — вузла нема, bad-kind — це не тека."""
    _precheck(pages)
    kind = next((f['kind'] for f in flatten(pages) if f['page'].get('id') == node_id), None)
    if kind is None:
        raise TreeError('not-found', f'page not found: {node_id}')
    if kind != 'folder':
        raise TreeError('bad-kind', 'only a folder can be ungrouped')
    return op_unwrap(pages, node_id)[0]


def op_set_kind(pages, node_id, kind):
    """Лагодить тип спадку: сторінка ↔ стан. Теку не міняємо — у неї немає
    файлів, а в сторінки є, і «перетворення» лише збрехало б про диск.

    Вхід цілим `validate` НЕ перевіряємо: легасі-дерево може бути вже зламане
    (`[p[c[d]]]` без kind — c виводиться станом із дитиною), а ця операція якраз
    його й лагодить. Вузька `_precheck` ловить лише id і невалідний kind."""
    if kind not in ('page', 'state'):
        raise TreeError('bad-kind', f'cannot set kind {kind!r}')
    _precheck(pages)
    t = copy.deepcopy(pages)
    node, _ = find_page(t, node_id)
    if node is None:
        raise TreeError('not-found', f'page not found: {node_id}')
    current = next(f['kind'] for f in flatten(t) if f['page'] is node)
    if current == 'folder':
        raise TreeError('bad-kind', 'a folder has no files and cannot become a page')
    if current == kind:
        return t                # нічого не міняємо й нічого не матеріалізуємо
    # НЕСУЧЕ для зламаного легасі-дерева: явні типи ДО зміни, інакше діти вузла
    # перевиведуться з його нового типу. `[p[c[d]]]`, c→page: без цього d стала б
    # станом (дитина сторінки), а з ним лишається сторінкою, як була.
    materialize(t)
    node['kind'] = kind
    validate(t)
    return t


def op_restore(pages, prev):
    """Повернути теки й типи з `prev` — дерева, яке панель бачила ДО чужого
    перезапису (fb-01102026-71980b) — не втративши того, що є в `pages` зараз.

    Правда про те, ЯКІ сторінки існують, — у `pages` (їх тримає диск), правда про
    ОРГАНІЗАЦІЮ (теки, стани, назви, порядок) — у `prev`:
      · тека з `prev` повертається завжди (у неї нема файлів, губити нічого);
      · сторінка/стан з `prev` лишається, лише якщо вона є в `pages`; зникла —
        її вцілілі діти піднімаються на її місце;
      · стан, що опинився без сторінки-предка, стає сторінкою (інакше validate);
      · вузли `pages`, яких нема в `prev` (нові сторінки скрипта), — у кінець
        свого теперішнього батька, якщо він у дереві, інакше в корінь.
    Повертає (дерево, [id тек, яких у `pages` не було]). Кривий `prev` —
    `bad-prev` (це вхід запиту, а не стан диска: не `corrupt`)."""
    if not isinstance(prev, list):
        raise TreeError('bad-prev', 'prev must be a list')
    try:
        _check_shape(prev)
        _precheck(prev)
    except TreeError as e:
        raise TreeError('bad-prev', str(e)) from None
    _precheck(pages)
    cur = flatten(pages)
    alive = {f['page']['id']: f['page'] for f in cur if f['kind'] != 'folder'}
    cur_folders = {f['page']['id'] for f in cur if f['kind'] == 'folder'}
    placed, restored = set(), []

    def build(nodes, parent_kind, in_page):
        out = []
        for n in nodes:
            nid = n.get('id')
            kind = kind_of(n, parent_kind)
            kids = _children_list(n)
            if kind == 'folder' and nid not in alive and nid not in placed:
                node = {k: v for k, v in n.items() if k != 'children'}
                node['kind'] = 'folder'
                placed.add(nid)
                if nid not in cur_folders:
                    restored.append(nid)
                node['children'] = build(kids, 'folder', in_page)
                out.append(node)
            elif kind != 'folder' and nid in alive and nid not in placed:
                node = {k: v for k, v in n.items() if k != 'children'}
                node['kind'] = kind if (kind != 'state' or in_page) else 'page'
                placed.add(nid)
                ch = build(kids, node['kind'], in_page or node['kind'] == 'page')
                if ch:
                    node['children'] = ch
                out.append(node)
            else:
                out.extend(build(kids, parent_kind, in_page))
        return out

    tree = build(prev, None, False)
    index = {}

    def reg(nodes, in_page):
        for n in nodes:
            here = in_page or n.get('kind') == 'page'
            index[n['id']] = (n, here)
            reg(n.get('children') or [], here)
    reg(tree, False)
    for f in cur:
        nid = f['page']['id']
        if nid in index:
            continue
        node = {k: v for k, v in f['page'].items() if k != 'children'}
        node['kind'] = f['kind']
        holder = index.get(f['parent'])
        if node['kind'] == 'state' and not (holder and holder[1]):
            node['kind'], holder = 'page', None
        dest = holder[0].setdefault('children', []) if holder else tree
        dest.append(node)
        index[nid] = (node, (holder[1] if holder else False) or node['kind'] == 'page')
    validate(tree)
    return tree, restored


def op_delete(pages, node_id, mode):
    """mode='all' — вузол з усім піддеревом; 'unwrap' — див. op_unwrap.
    Повертає (дерево, [відносні теки файлів до стирання])."""
    if mode == 'unwrap':
        return op_unwrap(pages, node_id)
    if mode != 'all':
        raise TreeError('bad-mode', f'unknown delete mode {mode!r}')
    _precheck(pages)
    t = copy.deepcopy(pages)
    node, sibs = find_page(t, node_id)
    if node is None:
        raise TreeError('not-found', f'page not found: {node_id}')
    # flatten([node]) тут безпечний: тека чи ні, від типу БАТЬКА не залежить
    # (явний kind або isGroup), а всі не-теки мають теку файлів.
    removed = [page_rel(f['page']) for f in flatten([node])
               if f['kind'] != 'folder' and page_rel(f['page'])]
    sibs.remove(node)
    validate(t)
    return t, _unreferenced(t, removed)


def remove_dirs(iter_dir, rels):
    """Стерти теки сторінок ПІСЛЯ запису дерева (див. delete_page).

    Повертає rel, яких НЕ стерто: відкинуті як небезпечні (не за правилом id —
    `../x` вивело б rmtree за межі ітерації, а '' — неявна main — стерло б САМУ
    ітерацію), зарезервовані (спільні теки ітерації) або ті, що не далися
    (права, файл замість теки). Теки, якої вже нема, — не збій. Операції вище небезпечних rel не віддають, але ця функція
    стирає, тож стоїть сама, а не на слово викликачів."""
    failed = []
    for rel in rels:
        # RESERVED_IDS: легасі-сторінка з id `assets`/`icons`/`fonts`/`shots`
        # (validate такі id дозволяє — лише НОВІ їх не отримують) стерла б
        # rmtree СПІЛЬНУ теку ітерації разом із чужими файлами.
        if (not isinstance(rel, str) or not _ID_RE.fullmatch(rel)
                or rel in RESERVED_IDS):
            failed.append(rel)
            continue
        try:
            shutil.rmtree(os.path.join(iter_dir, rel))
        except FileNotFoundError:
            continue
        except OSError:
            failed.append(rel)
    return failed


def page_version_tag(it_id, page):
    """Тег версії коментаря. Неявна 'main' → чистий iter_num (сумісність зі старими
    пінами). Явна сторінка → '<num>/<pageId>'."""
    m = re.match(r'it(\d+)$', it_id)
    num = m.group(1) if m else it_id
    if page.get('id') == IMPLICIT_ID:
        return num
    return f'{num}/{page["id"]}'


def validate(pages):
    """Унікальність id, непорожні назви, глибина ≤ MAX_DEPTH, правила типів.
    Кидає TreeError (нащадок ValueError) з машинним кодом."""
    seen = set()
    for pg in pages:
        _validate_node(pg, 1, seen, None, False)


def _validate_node(pg, depth, seen, parent_kind, in_page):
    if depth > MAX_DEPTH:
        raise TreeError('too-deep', f'depth > {MAX_DEPTH}')
    # isinstance першим: id «5»/None/відсутній інакше дав би TypeError з
    # fullmatch — сервер віддав би 500 замість зрозумілого bad-id.
    if not isinstance(pg.get('id'), str) or not _ID_RE.fullmatch(pg['id']):
        raise TreeError('bad-id', f'bad id: {pg.get("id")!r}')
    if pg['id'] in seen:
        raise TreeError('dup-id', f'duplicate id: {pg["id"]}')
    seen.add(pg['id'])
    # isinstance: `.strip()` на числі/списку — AttributeError, а не відмова з кодом
    if not isinstance(pg.get('name'), str) or not pg['name'].strip():
        raise TreeError('empty-name', f'empty name for {pg["id"]}')
    if 'kind' in pg and pg['kind'] not in KINDS:
        raise TreeError('bad-kind', f'bad kind: {pg["kind"]!r}')
    k = kind_of(pg, parent_kind)
    kids = _children_list(pg)
    if k == 'state':
        # Стан — варіант вигляду СТОРІНКИ: без сторінки-предка він нічий.
        if not in_page:
            raise TreeError('state-outside-page', f'state {pg["id"]} is not inside a page')
        if kids:
            raise TreeError('state-has-children', f'state {pg["id"]} has children')
    for ch in kids:
        _validate_node(ch, depth + 1, seen, k, in_page or k == 'page')
