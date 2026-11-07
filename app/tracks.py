"""Напрямки простору (етап 4d-1, спека 2026-11-04-space-tracks-design.md): чисте ядро без мережі й без імпорту `serve`.

Напрямок — одна «лінія роботи» простору з власною текою задач, типовим репозиторієм макетів, статичною ДС інспектора й
підписом: `{id, label, root, repo, ds}`. Задача несе `track` (id напрямку); старий ключ `profile` рантайм не читає (4d-4a).

Звідки беруться напрямки: масив `tracks` у `space.json` простору (`normalize`) — для всіх просторів, ЛІГА теж. Неявного
адаптера (з кореня старого `tasks.json`) у рантаймі більше нема: його копія живе ЛИШЕ в `liga_migrate` (приватні `_legacy_*`)
і потрібна кроку `liga-4d4a`; охоронець `NoTracksAdapter`.

Канонічні тут (`serve` користується ними й власних копій не має): правила мітки (`TAG_BAD`, `TAG_MAX_LEN`,
`clean_tag`, `read_tag` — раніше `serve._TAG_BAD`/`_clean_tag`/`_read_tag`), `ID_RE` (раніше `serve._PROFILE_KEY`),
`REPO_OK`/`repo_ok` (раніше `serve._REPO_OK`).
"""
import os
import re

import spaces

#: Ідентифікатор напрямку: ті самі малі літери, цифри й дефіс, що колись `serve._PROFILE_KEY`. `fullmatch`, не `match`:
#: `$`/`match` пропустили б хвіст `\n`.
ID_RE = re.compile(r'[a-z0-9-]{1,32}')
#: Не більше стільки напрямків у просторі: решта після двадцятого мовчки відкидається.
MAX_TRACKS = 20
#: Репозиторій макетів — друковний ASCII без пробілів і БЕЗ `-` на початку. ⛔ Урок `profile_repos`: репо з `-` на початку
#: git прочитав би як опцію (`--upload-pack=…`); значень репо — ні в текстах помилок, ні в журналах.
REPO_OK = re.compile(r'[\x21-\x2c\x2e-\x7e][\x21-\x7e]*')
#: Правила мітки (раніше `serve._TAG_BAD`): керівні C0/C1, кома, невидимі нульової ширини (U+200B–U+200F, U+2060–U+2064,
#: U+FEFF) і двоспрямовані керування (U+202A–U+202E, U+2066–U+2069): мітка з U+202E виглядала б не тим, чим є.
TAG_BAD = re.compile('[\\x00-\\x1f\\x7f-\\x9f,\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff]')
TAG_MAX_LEN = 32
#: Керівні знаки в шляху `root`: NUL ламає `realpath`, решта — явне сміття.
_PATH_BAD = re.compile('[\\x00-\\x1f\\x7f]')
#: Найдовший `root` у `space.json` (знаків); довший вважається відсутнім. `spaces` власної межі шляху не має.
ROOT_MAX = 1024


def clean_tag(raw):
    return ' '.join(raw.split())


def read_tag(raw):
    """Одна мітка для ЧИТАННЯ: очищена або `None` (не рядок, порожня, задовга, з комою чи керівним знаком — ті самі правила,
    що в `serve.normalize_tags`, але без винятків: читання не кидає)."""
    if not isinstance(raw, str) or TAG_BAD.search(raw.strip()):
        return None
    tag = clean_tag(raw)
    return tag if tag and len(tag) <= TAG_MAX_LEN else None


def repo_ok(raw):
    """Репозиторій за `REPO_OK` — обрізаний рядок, інакше `''` (не рядок, порожній, з пробілом, не ASCII, з `-` на початку)."""
    if not isinstance(raw, str):
        return ''
    s = raw.strip()
    return s if REPO_OK.fullmatch(s) else ''


def _is_id(v):
    return isinstance(v, str) and ID_RE.fullmatch(v) is not None


def _norm_root(raw, space_path):
    """`root` напрямку → абсолютний шлях або `None`. Приймається абсолютний, `~` чи `~/…` (інші `~імʼя` — звичайна відносна
    назва) і відносний до шляху простору; не рядок, порожній, довший за `ROOT_MAX`, із керівним знаком — `None`.
    ⛔ Відносний `../..` нормалізується ДО перевірки: інакше `mobile/../../../usr` обійшов би відсів системних тек.
    Прийнятність — ТА САМА, що для шляху простору: `spaces.check_new_path` (без записів реєстру, тож порівнянь
    `path-registered`/`path-overlap` нема): системні теки й підтеки за текстом і `realpath`, надто широкий (домівка чи її
    предок, `/`), приховані теки й `Library` у домівці, тека інструмента, файл замість теки. Слабшої копії правил тут нема."""
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s or len(s) > ROOT_MAX or _PATH_BAD.search(s):
        return None
    if s == '~' or s.startswith('~/'):
        s = os.path.expanduser(s)
        if s.startswith('~'):
            return None
    if not os.path.isabs(s):
        if not isinstance(space_path, str) or not os.path.isabs(space_path):
            return None
        s = os.path.join(space_path, s)
    s = os.path.normpath(s)
    try:
        ok, why = spaces.check_new_path(s, {'spaces': []}, [])
    except (OSError, ValueError):             # помилка файлової системи — відмова, не пропуск
        return None
    return ok if why is None else None


def normalize(raw, space_path, roots=True):
    """`tracks` з `space.json` → `[{id, label, root, repo, ds}]`. НЕ кидає на жодному JSON: поганий запис мовчки відкидається,
    решта працює; поле, що не пройшло перевірку, вважається відсутнім (`root: None`, `repo: ''`, `ds: ''`).

    - не список → `[]`; запис не словник, `id` поза `ID_RE`, дубль `id` (перший перемагає) → запис відкинуто;
    - `label` — за правилами мітки (`read_tag`), інакше `id`;
    - `root` — див. `_norm_root` (уже розгорнутий в абсолютний шлях, прийнятний за правилами `spaces`); `repo` — `repo_ok`; `ds` — за `ID_RE`;
    - не більше `MAX_TRACKS` напрямків (перші).

    `roots=False` — корені НЕ перевіряються (кожен `root: None`, файлової системи не торкаємось): для читача, якому корені
    не потрібні (`GET /api/spaces` віддає лише `id` і `label`). ⛔ Перевірка кореня — це `realpath`/`stat` по кожному напрямку, а
    корінь може лежати на відімкненому чи повільному томі: список просторів не має чекати на нього."""
    if not isinstance(raw, list):
        return []
    out, seen = [], set()
    try:
        for rec in raw:
            if not isinstance(rec, dict):
                continue
            tid = rec.get('id')
            if not _is_id(tid):
                continue
            if tid in seen:
                continue
            seen.add(tid)
            ds = rec.get('ds')
            out.append({'id': tid,
                        'label': read_tag(rec.get('label')) or tid,
                        'root': _norm_root(rec.get('root'), space_path) if roots else None,
                        'repo': repo_ok(rec.get('repo')),
                        'ds': ds if _is_id(ds) else ''})
            if len(out) >= MAX_TRACKS:
                break
    except (RecursionError, MemoryError):     # надто глибока чи величезна вкладеність — не обвал, а «нема напрямків»
        return []
    return out


def adapter_applies(raw, path):
    """Чи діє неявний адаптер напрямків ЛІГИ на цьому `space.json` (`raw` — вміст ключа `tracks` або `None`): напрямків нема
    (`None`) або список непридатний (`normalize` дає порожнє). Живе лише для кроку `liga-4d4a`; ⛔ рантайм його не кличе
    (охоронець `NoTracksAdapter`)."""
    return raw is None or not normalize(raw, path, roots=False)


def default_id(tracks, raw):
    """Напрямок за замовчуванням: `raw` з переліку → він; інакше перший; порожній перелік → `None`."""
    ids = [t['id'] for t in tracks]
    if isinstance(raw, str) and raw in ids:
        return raw
    return ids[0] if ids else None


def of_task(task):
    """Напрямок задачі — збережений РЯДОК `track` (4d-4a: `profile` з записів більше не читається). Без звірки з `ID_RE`:
    значення вільне, перевірка шаблону — справа того, хто читає. Не словник, не рядок чи порожній — `None`."""
    if not isinstance(task, dict):
        return None
    v = task.get('track')
    return v if isinstance(v, str) and v else None


def find(tracks, tid):
    """Напрямок за id або `None` (id не рядок — теж `None`)."""
    if not isinstance(tid, str):
        return None
    for t in tracks:
        if t['id'] == tid:
            return t
    return None


def label_tag(tracks, task):
    """Похідна мітка задачі (рядок) або `None`; список `[tag]` / `[]` складає той, хто кличе (`serve.task_tags`).

    Напрямок знайдено → його `label`; не знайдено, але id є → сам id (паритет «невідомий — як є»). Усе проходить правила мітки
    (`read_tag`): ⛔ діалог правки заповнюється поточними мітками, і значення з комою чи на 300 знаків після збереження
    розпалося б або не пройшло `bad-tags`; такий напрямок — без похідної мітки."""
    v = of_task(task)
    if v is None:
        return None
    t = find(tracks, v)
    if t is None:
        return read_tag(v)
    return read_tag(t.get('label')) or read_tag(v)
