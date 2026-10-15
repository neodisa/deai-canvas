"""Вбудований модуль `css-tokens` (роль `tokens`): токени дизайн-системи з ОДНОГО CSS-файла.

Інспектор звіряє значення макета з токенами ДС; цей модуль віддає їх у формі, яку читає
`dsIndex` (`{імʼя: [значення…]}`), із файла, на який вказує налаштування `file`.

`server.py` виконується ядром через `exec` у свіжий модуль: лише stdlib, без імпорту `serve`,
`deai_modules` чи сусідніх файлів, без читання власного шляху.

Що вважається токеном
  * декларація `--імʼя: значення` у правилі РІВНЯ КОРЕНЯ: крайній складений селектор (суб'єкт) хоч
    одного селектора списку — `html`, `:root` або атрибут `[data-…theme…]` (`[data-theme=dark]`,
    `[data-bs-theme=dark]` Bootstrap 5.3, `[data-color-theme]`). `[data-theme=dark] .card { --x }`
    задає змінну картці, а не темі, тож токеном не є, а `html.dark`, `:root[data-theme=dark]`,
    `.dark :root` — є. Голий клас (`.dark { … }`) НЕ береться навмисно: клас стоїть на будь-якому
    елементі, і токени змішалися б із локальними змінними компонентів;
  * декларації ПРЯМО в `@theme { … }` (Tailwind v4; також `@theme inline|static|default`) — токени
    самі по собі, а скидання простору імен `--color-*: initial` (імʼя з `*`) — ні;
  * правила будь-якої вкладеності в at-правилах (`@media`, `@layer`, `@supports`, `@container`,
    `@scope`, `@-moz-document`…) розгортаються — кожне правило оцінюється за власним селектором, тож
    `@keyframes`/`@font-face`/`@page` токенів не дають; декларації ПРЯМО в умовних групах
    (`@media`/`@layer`/`@supports`/`@container`/`@document`) — токени, лише коли група вкладена в сам
    рядок кореня (CSS nesting: `:root { @media … { --a: 1 } &[data-theme=x] {…} }`);
  * значення збираються СПИСКОМ на імʼя (теми, медіа), без повторів, у порядку появи. Коментарі
    прибираються, пробіли стискаються, `!important` відкидається. `;` і `}` усередині лапок,
    `url(…)`, дужок `()`/`[]` і значення-блоку `--x: { … }` значення не ріжуть; рядок без
    закривної лапки (до кінця рядка) робить недійсною всю декларацію — як у браузері;
  * `var(--x)` розгортається, якщо `--x` визначено в ЦЬОМУ файлі (до `MAX_HOPS` стрибків, без
    циклів; значення-список цілі множиться на теми), запасне значення `var(--x, …)` ігнорується:
    невизначена змінна може бути задана деінде. Не вдалось розгорнути ХОЧА Б ОДНЕ значення токена
    (цикл, невизначена, надто глибоко, кривий `var()`, стеля нижче) — список токена порожній: імʼя
    відоме, а значення звіряти нема з чим (неповний список дав би хибне «перевизначено» для теми, що
    в нього не потрапила). Стелі (множення значень інакше вибухає пам'яттю й часом): `MAX_COMBOS`
    комбінацій в одному значенні, `MAX_VALUES` — у всіх `var()`-значень одного токена разом,
    `MAX_EXPANDED` — у всіх токенах файла разом (порядок — за першою появою імені; значення без
    `var()` не рахуються). `@import` не відстежується.

Читання: лише звичайний файл (`S_ISREG`, перевірка на ДЕСКРИПТОРІ — між `stat` і `open` файл не
підміниш на FIFO), ≤ 2 МіБ (читаємо не більше за ліміт + 1 байт), `utf-8` з толерантністю до BOM і
биттих байтів. Кеш — за (шлях, mtime_ns, розмір), обмежений `_CACHE_MAX` записів.
"""
import itertools
import os
import re
import stat
import threading

MAX_BYTES = 2 * 1024 * 1024
MAX_HOPS = 5            # скільки разів поспіль `var()` може вести до іншого `var()`
MAX_COMBOS = 64         # комбінацій теми·теми в ОДНОМУ значенні; більше — не розгортаємо
MAX_VALUES = 1024       # скільки комбінацій усіх `var()`-значень ОДНОГО токена разом; більше — `[]`
MAX_EXPANDED = 20000    # скільки комбінацій усіх токенів ФАЙЛА разом; решта токенів із `var()` — `[]`
_CACHE_MAX = 8

#: Умовні групові at-правила: декларації прямо в них належать правилу, у якому вони вкладені.
_GROUP_AT = frozenset(('media', 'supports', 'layer', 'container', 'document'))
#: At-правила, декларації яких — токени самі по собі (Tailwind v4: `@theme { --color-brand: … }`).
_TOKEN_AT = frozenset(('theme',))


class TokensError(ValueError):
    """Файл не прочитати чи не придатний; текст короткий і без шляху."""


# ----------------------------------------------------------------------------------- лексика

#: Лапки й нецитований `url(…)` — «атоми»: що всередині, структури не ріже. Рядок без закриття
#: кінчається на розриві рядка (`bad`: як bad-string у CSS він робить недійсною всю декларацію).
#: Коментар `/* */` розпізнається лише ПОЗА атомами.
_DQ = r'"(?:[^"\\\n]|\\[\s\S])*'
_SQ = r"'(?:[^'\\\n]|\\[\s\S])*"
_STR_OK = _DQ + '"|' + _SQ + "'"
_STR_BAD = _DQ + '|' + _SQ
_STR = '(?:' + _DQ + '"?|' + _SQ + "'?)"
_URL = r'''(?<![\w-])url\((?=\s*[^\s"'])(?:[^)\\]|\\[\s\S])*\)?'''
_BAD = '\ufdd0'          # на місці bad-string у тексті декларації: така декларація відкидається
_TOK = re.compile(
    r'(?P<str>' + _STR_OK + r')'
    r'|(?P<bad>' + _STR_BAD + r')'
    r'|(?P<com>/\*[\s\S]*?(?:\*/|\Z))'
    r'|(?P<url>' + _URL + r')'
    r'|(?P<op>[{};()\[\]])'
    r'|(?P<ws>\s+)'
    r'|(?P<txt>\\[\s\S]|[^"\'/{};()\[\]\\uU\s]+|[\s\S])',
    re.I)
_ATOM = re.compile(_STR + '|' + _URL, re.I)
_STRINGS = re.compile(_STR)

_DECL = re.compile(r'(--[^\s:;{}]+)\s*:([\s\S]*)\Z')
_DECL_START = re.compile(r'--[^\s:;{}]+\s*:')
#: `!important` у кінці значення. Без `\s*` ПЕРЕД `!`: невивернений `sub` із ним — квадрат на довгих
#: проміжках пробілів (100 КБ у лапках = 7 с); значення перед ним уже `strip()`-нуте.
_IMPORTANT = re.compile(r'!\s*important\Z', re.I)
_AT = re.compile(r'@([\w-]+)')
#: Складений селектор «рівня кореня» (рядки в лапках вже замінено на `""`): `html`, `:root` чи атрибут
#: `[data-…theme…]` (`[data-theme]`, `[data-bs-theme=dark]`). Голий клас (`.dark`) — ні.
_ROOTISH = re.compile(r'(?<![\w.#:\[-])html(?![\w-])|:root(?![\w-])|\[\s*data-[\w-]*theme', re.I)
_VAR_OPEN = re.compile(r'(?<![\w-])var\(', re.I)


def _top_level(s, is_sep):
    """Ріже `s` по символах, для яких `is_sep(c)`, лише на верхньому рівні (поза `()`, `[]`, лапками)."""
    out, cur, depth, quote, i, n = [], [], 0, None, 0, len(s)
    while i < n:
        c = s[i]
        if quote:
            cur.append(c)
            if c == '\\' and i + 1 < n:
                i += 1
                cur.append(s[i])
            elif c == quote:
                quote = None
        elif c in '"\'':
            quote = c
            cur.append(c)
        elif c == '\\' and i + 1 < n:
            cur.append(c)
            i += 1
            cur.append(s[i])
        elif c in '([':
            depth += 1
            cur.append(c)
        elif c in ')]':
            depth = max(0, depth - 1)
            cur.append(c)
        elif depth == 0 and is_sep(c):
            out.append(''.join(cur))
            cur = []
        else:
            cur.append(c)
        i += 1
    out.append(''.join(cur))
    return out


def _is_combinator(c):
    return c in ' \t\r\n\f>+~'


def _qualifies(prelude, parent_q):
    """Чи задають декларації цього правила токени: крайній складений селектор хоч одного селектора
    списку — `:root`, `html` чи `[data-theme…]`; у вкладеному в такий рядок правилі ще й `&` у ньому."""
    for sel in _top_level(prelude, lambda c: c == ','):
        parts = [p for p in _top_level(sel, _is_combinator) if p]
        if not parts:
            continue
        subject = _STRINGS.sub('""', parts[-1])
        if _ROOTISH.search(subject) or (parent_q and '&' in subject):
            return True
    return False


def _frame(prelude, parent_q):
    """`q` для блоку з прелюдією `prelude`, вкладеного в блок з `parent_q`: чи є декларації тут
    токенами. `@theme` (Tailwind v4) — завжди токени; умовне групове at-правило (`@media`…)
    успадковує `q` рядка, у якому вкладене (CSS nesting: `:root { @media … { --a: 1 } }`); будь-яке інше at-правило (`@font-face`, `@keyframes`,
    `@scope`, `@-moz-document`…) токенів САМЕ ПО СОБІ не дає, але його вміст проглядається: правило
    всередині (`@scope (…) { :root { … } }`) кваліфікується за власним селектором."""
    if prelude.startswith('@'):
        m = _AT.match(prelude)
        name = m.group(1).lower() if m else ''
        return name in _TOKEN_AT or (parent_q and name in _GROUP_AT)
    return _qualifies(prelude, parent_q)


# -------------------------------------------------------------------------------------- розбір

def _parse_raw(text):
    """`{імʼя: {сире значення: None}}` — як у файлі (без `var()`-розгортання), у порядку появи."""
    raw = {}
    frames = [False]        # `q` кожного відкритого блоку; [0] — верхній рівень
    buf = []
    pdepth = 0              # глибина () і []: усередині `;` `{` `}` — просто текст
    vdepth = 0              # глибина {} усередині значення `--x: { … }`

    def take():
        s = ''.join(buf).strip()
        buf.clear()
        return s

    def decl(s):
        if not frames[-1] or not s.startswith('--') or _BAD in s:
            return
        m = _DECL.match(s)
        if not m:
            return
        if '*' in m.group(1):                       # `@theme { --color-*: initial }` — скидання простору імен
            return
        vals = raw.setdefault(m.group(1), {})       # dict як впорядкована множина: без повторів і без O(n²)
        v = _IMPORTANT.sub('', m.group(2).strip()).strip()
        if v:
            vals[v] = None

    for m in _TOK.finditer(text):
        kind, s = m.lastgroup, m.group()
        if kind in ('com', 'ws'):                      # коментар — роздільник, як і пробіл
            if buf and not buf[-1].endswith(' '):
                buf.append(' ')
            continue
        if kind != 'op':
            buf.append(_BAD if kind == 'bad' else s)
            continue
        if s in '([':
            pdepth += 1
            buf.append(s)
        elif s in ')]':
            pdepth = max(0, pdepth - 1)
            buf.append(s)
        elif pdepth:
            buf.append(s)
        elif s == '{':
            if vdepth:
                vdepth += 1
                buf.append(s)
                continue
            pre = take()
            if _DECL_START.match(pre):                 # `--x: { … }` — це значення, а не блок
                buf.extend((pre, '{'))
                vdepth = 1
            else:
                frames.append(_frame(pre, frames[-1]))
        elif s == '}':
            if vdepth:
                vdepth -= 1
                buf.append(s)
                continue
            decl(take())
            if len(frames) > 1:
                frames.pop()
        elif vdepth:                                   # `;`
            buf.append(s)
        else:
            decl(take())
    decl(take())
    return raw


def _segments(value):
    """`value` → список рядків і `('var', '--імʼя')`; `None`, якщо `var()` кривий чи не закритий.
    `var(` у лапках чи в `url(…)` — звичайний текст."""
    segs, lit, i, n = [], [], 0, len(value)
    while i < n:
        a = _ATOM.match(value, i)
        if a:
            lit.append(a.group())
            i = a.end()
            continue
        v = _VAR_OPEN.match(value, i)
        if not v:
            lit.append(value[i])
            i += 1
            continue
        j, depth, comma = v.end(), 1, None
        while j < n and depth:
            a = _ATOM.match(value, j)
            if a:
                j = a.end()
                continue
            c = value[j]
            if c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
            elif c == ',' and depth == 1 and comma is None:
                comma = j
            j += 1
        if depth:
            return None                                # не закрито
        name = value[v.end():(comma if comma is not None else j - 1)].strip()
        if lit:
            segs.append(''.join(lit))
            lit = []
        segs.append(('var', name))
        i = j
    if lit:
        segs.append(''.join(lit))
    return segs


def _fill(per_value, done, budget):
    """Усі значення токена з підставленими цілями `var()`, або `None` — не розгортається (поки: якусь
    ціль ще не розгорнуто; назавжди: забагато комбінацій в одному значенні, в токені чи в файлі —
    стелі не слабшають, тож наступні раунди дадуть те саме, але дешево). Спершу перевірка готовності й стель на всіх значеннях (дешево), потім — саме добуток; стеля
    рахує КОМБІНАЦІЇ, а не різні результати: дубльовані розгортання не лишають слідів у виході, але
    коштують часу. Значення без `var()` не рахуються (вихід не більший за вхід). У `budget[0]` лишок
    стелі файла; списується лише при успіху."""
    plans, spent = [], 0
    for segs in per_value:
        parts, size, has_var = [], 1, False
        for sg in segs:
            if isinstance(sg, str):
                parts.append((sg,))
                continue
            vals = done.get(sg[1])
            if not vals:
                return None
            has_var = True
            parts.append(vals)
            size *= len(vals)
            if size > MAX_COMBOS:
                return None
        if has_var:
            spent += size
            if spent > MAX_VALUES or spent > budget[0]:
                return None
        plans.append(parts)
    out = {}
    for parts in plans:
        for combo in itertools.product(*parts):
            v = ''.join(combo).strip()
            if v:
                out[v] = None
    budget[0] -= spent
    return list(out) or None


def _resolve(raw):
    """Розгорнути `var()` раундами: раунд `k` розгортає імена, чиї цілі вже розгорнуто в раундах
    `< k` (тобто ланцюжок із `k` стрибків). Цикл і невизначена ціль не розгортаються ніколи; після
    `MAX_HOPS` раундів решта — надто глибока. Без рекурсії й без експоненти; сумарна робота обмежена
    `MAX_VALUES` на токен і `MAX_EXPANDED` на файл (порядок — за першою появою імені)."""
    info = {}
    for name, vals in raw.items():
        per = [_segments(v) for v in vals]
        info[name] = per if vals and all(p is not None for p in per) else None
    done = {}
    budget = [MAX_EXPANDED]
    for _ in range(MAX_HOPS + 1):
        fresh = {}
        for name, per in info.items():
            if per is None or name in done:
                continue
            got = _fill(per, done, budget)
            if got is not None:
                fresh[name] = got
        if not fresh:
            break
        done.update(fresh)
    return {name: list(done.get(name, ())) for name in raw}


def parse_css_tokens(text):
    """Текст CSS → `{імʼя: [значення…]}` (імена з `--`). Порожній список — імʼя відоме, а значення
    не розгорнулось (див. докстрінг модуля)."""
    return _resolve(_parse_raw(text))


# ------------------------------------------------------------------------------------ читання

_LOCK = threading.Lock()
_CACHE = {}             # (шлях, mtime_ns, розмір) → {імʼя: [значення]}; найстаріші — першими


def _too_big():
    return TokensError(f'file: bigger than {MAX_BYTES // (1024 * 1024)} MiB')


def _open_regular(path):
    """Відкритий дескриптор ЗВИЧАЙНОГО файла й його `fstat`. `O_NONBLOCK` — щоб `open` FIFO не повис;
    перевірка типу — на дескрипторі, а не на шляху (немає вікна підміни)."""
    flags = os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_NOCTTY', 0) | getattr(os, 'O_BINARY', 0)
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        raise TokensError('file: not found') from None
    except ValueError:                                  # NUL у шляху, непередаваний сурогат: це `ValueError`, не `OSError`
        raise TokensError('file: bad path') from None
    except OSError as e:
        raise TokensError(f'file: cannot be opened ({e.strerror or type(e).__name__})') from None
    try:
        try:
            st = os.fstat(fd)
        except OSError as e:
            raise TokensError(f'file: cannot be read ({e.strerror or type(e).__name__})') from None
        if not stat.S_ISREG(st.st_mode):
            raise TokensError('file: not a regular file')
        if st.st_size > MAX_BYTES:
            raise _too_big()
    except BaseException:
        os.close(fd)
        raise
    return fd, st


def _read_all(fd):
    chunks, left = [], MAX_BYTES + 1
    try:
        while left > 0:
            b = os.read(fd, min(left, 1 << 20))
            if not b:
                break
            chunks.append(b)
            left -= len(b)
    except OSError as e:
        raise TokensError(f'file: cannot be read ({e.strerror or type(e).__name__})') from None
    data = b''.join(chunks)
    if len(data) > MAX_BYTES:
        raise _too_big()
    return data


def _copy(tokens):
    return {k: list(v) for k, v in tokens.items()}


def tokens(ctx):
    """`{"tokens": {імʼя: [значення…]}, "source": імʼя файла}`. Файл без токенів — порожній словник
    (не помилка: рішення «чи це ДС» за споживачем); не прочитати — `TokensError`."""
    path = ((ctx or {}).get('settings') or {}).get('file')
    if not isinstance(path, str) or not path.strip():
        raise TokensError('file: not set')
    fd, st = _open_regular(path)
    try:
        key = (path, st.st_mtime_ns, st.st_size)
        with _LOCK:
            hit = _CACHE.get(key)
        if hit is None:
            hit = parse_css_tokens(_read_all(fd).decode('utf-8-sig', 'replace'))
            with _LOCK:
                for old in [k for k in _CACHE if k[0] == path]:     # старі версії цього ж файла
                    del _CACHE[old]
                _CACHE[key] = hit
                while len(_CACHE) > _CACHE_MAX:
                    del _CACHE[next(iter(_CACHE))]
    finally:
        os.close(fd)
    return {'tokens': _copy(hit), 'source': os.path.basename(path)}


def check(ctx):
    """Без побічних ефектів: файл читається й має ≥1 токен."""
    try:
        res = tokens(ctx)
    except TokensError as e:
        return {'ok': False, 'error': str(e)}
    n = len(res['tokens'])
    if not n:
        return {'ok': False, 'error': 'no --custom-property declarations in :root, html or [data-theme] rules'}
    return {'ok': True, 'detail': f'{n} tokens'}
