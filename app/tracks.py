"""Напрямки простору (етап 4d-1, спека 2026-11-04-space-tracks-design.md): чисте ядро без мережі й без імпорту `serve`.

Напрямок — одна «лінія роботи» простору з власною текою задач, типовим репозиторієм макетів, статичною ДС інспектора й
підписом: `{id, label, root, repo, ds}`. Задача несе `track` (id напрямку); до 4d-4 старий ключ `profile` — його синонім.

Звідки беруться напрямки:
- звичайний простір — масив `tracks` у його `space.json` (`normalize`);
- простір ЛІГИ — неявний адаптер `legacy_tracks(cfg)` з кореня старого `tasks.json` (`design_work_roots`,
  `design_work_root`, `profile_repos`). ⛔ Адаптер ТИМЧАСОВИЙ: у 4d-3 міграція запише ті самі напрямки в `space.json`
  простору ЛІГИ, і тоді `_LEGACY_LABELS` та дефолт `united` підуть звідси разом з адаптером. Поки він живе, паритет з 0.14.0
  понад усе: усе, що колись робили `serve.work_root`, `serve.profile_repos` і похідна мітка `task_tags`, має
  відтворюватися тут байт-у-байт (знімок `tests/fixtures/tracks/before-4d1.json`).

Канонічні тут (Task 3 перемикає `serve` на них, а свої копії прибирає): правила мітки (`TAG_BAD`, `TAG_MAX_LEN`,
`clean_tag`, `read_tag` — раніше `serve._TAG_BAD`/`_clean_tag`/`_read_tag`), `ID_RE` (раніше `serve._PROFILE_KEY`),
`REPO_OK`/`repo_ok` (раніше `serve._REPO_OK`), `legacy_root` (раніше `serve.work_root`), `legacy_repos` (раніше
`serve.profile_repos` без читання файла), `FALLBACK_ROOT` (раніше `serve.FALLBACK_WORK_ROOT`).
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
#: Останній рубіж кореня задач ЛІГИ, коли в `tasks.json` нема нічого. Історична тека United — саме тому вона й муляє: у ній
#: лежали задачі всіх трьох напрямків.
FALLBACK_ROOT = '~/deai-work'
#: Напрямки ЛІГИ, що є завжди (порядок = порядок переліку адаптера) і дефолт для задачі без напрямку.
_LEGACY_IDS = ('united', 'liga360', 'seo')
_LEGACY_DEFAULT = 'united'
#: Підписи адаптера ЛІГИ (раніше `serve._LEGACY_PROFILE_TAGS`): невідомий напрямок показується як є. Піде в 4d-3.
_LEGACY_LABELS = {'united': 'United', 'liga360': 'LIGA360', 'seo': 'SEO'}
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


def normalize(raw, space_path):
    """`tracks` з `space.json` → `[{id, label, root, repo, ds}]`. НЕ кидає на жодному JSON: поганий запис мовчки відкидається,
    решта працює; поле, що не пройшло перевірку, вважається відсутнім (`root: None`, `repo: ''`, `ds: ''`).

    - не список → `[]`; запис не словник, `id` поза `ID_RE`, дубль `id` (перший перемагає) → запис відкинуто;
    - `label` — за правилами мітки (`read_tag`), інакше `id`;
    - `root` — див. `_norm_root` (уже розгорнутий в абсолютний шлях, прийнятний за правилами `spaces`); `repo` — `repo_ok`; `ds` — за `ID_RE`;
    - не більше `MAX_TRACKS` напрямків (перші)."""
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
                        'root': _norm_root(rec.get('root'), space_path),
                        'repo': repo_ok(rec.get('repo')),
                        'ds': ds if _is_id(ds) else ''})
            if len(out) >= MAX_TRACKS:
                break
    except (RecursionError, MemoryError):     # надто глибока чи величезна вкладеність — не обвал, а «нема напрямків»
        return []
    return out


def default_id(tracks, raw):
    """Напрямок за замовчуванням: `raw` з переліку → він; інакше перший; порожній перелік → `None`."""
    ids = [t['id'] for t in tracks]
    if isinstance(raw, str) and raw in ids:
        return raw
    return ids[0] if ids else None


def of_task(task):
    """Напрямок задачі — збережений РЯДОК: `track`, інакше `profile` (синонім до 4d-4). Без звірки з `ID_RE`: ЛІГА приймає
    будь-який рядок як є (`'United'` теж, як 0.14.0), а перевірка шаблону — справа того місця, що читає (звичайний простір,
    `?ds=`). Не словник, не рядок чи порожній — `None`; порожній/не рядок `track` не затуляє валідний `profile`."""
    if not isinstance(task, dict):
        return None
    for key in ('track', 'profile'):
        v = task.get(key)
        if isinstance(v, str) and v:
            return v
    return None


def find(tracks, tid):
    """Напрямок за id або `None` (id не рядок — теж `None`)."""
    if not isinstance(tid, str):
        return None
    for t in tracks:
        if t['id'] == tid:
            return t
    return None


def label_tag(tracks, task, legacy=False):
    """Похідна мітка задачі (рядок) або `None`; список `[tag]` / `[]` складає той, хто кличе (`serve.task_tags`).

    Звичайний простір: напрямок знайдено → його `label`; не знайдено, але id є → сам id (паритет «невідомий — як є»). ЛІГА
    (`legacy=True`, неявний адаптер): значення — вільний рядок, не обовʼязково з переліку, тож береться `_LEGACY_LABELS.get(v,
    v)` без звірки з `tracks`. Обидва шляхи проходять ті самі правила мітки (`read_tag`): ⛔ діалог правки заповнюється
    поточними мітками, і значення з комою чи на 300 знаків після збереження розпалося б або не пройшло `bad-tags`; такий
    напрямок — без похідної мітки."""
    v = of_task(task)
    if v is None:
        return None
    if legacy:
        return read_tag(_LEGACY_LABELS.get(v, v))
    t = find(tracks, v)
    if t is None:
        return read_tag(v)
    return read_tag(t.get('label')) or read_tag(v)


# ── адаптер ЛІГИ: корінь старого `tasks.json` → напрямки ──────────────────────────────────────────────────────────────

def _legacy_roots(cfg):
    """`design_work_roots` ЛІГИ. ⛔ Не словник → `{}` (0.14.0 тут падав `AttributeError`; свідома відмінність спеки §6.4: спільний
    корінь замість обвалу)."""
    raw = cfg.get('design_work_roots') if isinstance(cfg, dict) else None
    return raw if isinstance(raw, dict) else {}


def _legacy_fallback(cfg):
    shared = cfg.get('design_work_root') if isinstance(cfg, dict) else None
    return os.path.expanduser(shared if isinstance(shared, str) and shared else FALLBACK_ROOT)


def legacy_root(cfg, value):
    """Корінь робочих тек ДЛЯ ЦЬОГО НАПРЯМКУ ЛІГИ (раніше `serve.work_root(cfg, profile)`), з розгорнутим `~`.

    Вимога користувача 31.08.2026: три напрямки — три теки і три репозиторії. Порядок: свій корінь напрямку →
    спільний `design_work_root` → історичний фолбек. ⛔ Напрямок без власного кореня НЕ вигадується (і не береться з
    дефолтного): краще чесно покласти в спільний корінь і сказати про це (`bin/roots.py`), ніж створити теку за вигаданим
    шляхом. `value` — що завгодно (`'United'`, `''`, число, `None`): невідоме — спільний корінь. Не кидає на поганому `cfg`.

    Свідома відмінність від 0.14.0: НЕ рядок у власному корені напрямку чи в `design_work_root` (число, список) раніше
    давав `TypeError` у `expanduser` (500); тепер таке значення вважається відсутнім і діє наступна ланка ланцюга
    (власний → спільний → `~/deai-work`)."""
    own = _legacy_roots(cfg).get(value) if isinstance(value, str) else None
    if isinstance(own, str) and own:
        return os.path.expanduser(own)
    return _legacy_fallback(cfg)


def legacy_repos(cfg):
    """Таблиця «напрямок → репозиторій макетів» ЛІГИ з кореня `tasks.json` (раніше `serve.profile_repos` без читання файла).
    Ключ — за `ID_RE`, репо — `repo_ok` (обрізане); погані пари відкидаються, `cfg` не словник / ключа нема / не словник —
    `{}`. ⛔ Структура в усіх напрямків одна — `mockup/<task-id>`, тому напрямки розходяться лише репозиторієм, а не логікою
    (урок колишньої константи `PROFILE_REPOS`). Значень — ні в текстах, ні в журналах."""
    raw = cfg.get('profile_repos') if isinstance(cfg, dict) else None
    if not isinstance(raw, dict):
        return {}
    out = {}
    for k, v in raw.items():
        r = repo_ok(v)
        if r and _is_id(k):
            out[k] = r
    return out


def legacy_tracks(cfg):
    """Неявні напрямки ЛІГИ → `(tracks, default_id, fallback_root)`.

    Перелік id: `united`, `liga360`, `seo`, далі ключі `design_work_roots` і `profile_repos` (лише за `ID_RE`, у такому
    порядку, без дублів). `root` — `legacy_root` (свій → спільний → `~/deai-work`, розгорнутий); `repo` — з `legacy_repos`
    або `''`; `label` — `_LEGACY_LABELS` або `id`; `ds` = `id` (вендорний інспектор сам каже «ДС нема» для невідомого);
    дефолт — `united`. `fallback_root` — корінь для будь-якого значення поза переліком (`'United'`, невідомий, `None`):
    не корінь дефолтного напрямку (спека §6.1). Перелік не обмежений `MAX_TRACKS`: адаптер дзеркалить довільний конфіг, а
    репо 21-го ключа 0.14.0 теж віддавав. Не кидає на поганому `cfg`."""
    ids = list(_LEGACY_IDS)
    seen = set(ids)
    raw_repos = cfg.get('profile_repos') if isinstance(cfg, dict) else None
    for src in (_legacy_roots(cfg), raw_repos if isinstance(raw_repos, dict) else {}):
        for k in src:
            if _is_id(k) and k not in seen:
                seen.add(k)
                ids.append(k)
    repos = legacy_repos(cfg)
    tracks = [{'id': i, 'label': _LEGACY_LABELS.get(i, i), 'root': legacy_root(cfg, i),
               'repo': repos.get(i, ''), 'ds': i} for i in ids]
    return tracks, _LEGACY_DEFAULT, _legacy_fallback(cfg)
