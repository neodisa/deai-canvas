"""Конфіг УСТАНОВКИ (етап 4c-1): старий файл задач ЛІГИ й адреса/ключ Supabase з нього.

Жив у `serve.py`; переїхав сюди, щоб ядро дашборда (`app/dashboard.py`) і CLI-пушер (`bin/overview_push.py`) читали той самий
конфіг БЕЗ імпорту `serve` (він тягне сервер, мережу й увесь стан). `serve` реекспортує імена: інструменти (`ops/`, `bin/`)
і тести беруть їх звідти, а `serve.supabase_config` лишається тонкою обгорткою — точкою підміни для тестів.
"""
import json
import os
import re

import implicit  # закон ізоляції (`implicit.isolated()`); імпортує лише `os` — циклу з ядром нема
import spaces  # простори машини: де лежить старий файл задач (`spaces.legacy_tasks_file`)


def legacy_tasks_path():
    """Старий файл задач (простір `legacy`) — для інструментів ЛІГА (доктор, `roots.py`,
    `ops/reseal_gate.py`): вони працюють із ним, у який би простір не дивився запит."""
    return spaces.legacy_tasks_file()


def load_legacy_tasks():
    """Старий файл як є; нема — `FileNotFoundError`, як `load_tasks` до просторів."""
    with open(legacy_tasks_path(), encoding='utf-8') as f:
        return json.load(f)


#: Кошик Storage ЛІГИ для скріншотів пінів: картка Teams бере `meta.shotUrl` звідти (як старий адаптер 0.9.0). Джерело правди —
#: тут (4d-3b): його потребує й міграція ЛІГИ (`liga_migrate`), яка не імпортує `serve`; `serve.LEGACY_SHOTS_BUCKET` — аліас.
LEGACY_SHOTS_BUCKET = 'overview-thumbs'

_SUPABASE_URL_RE = re.compile(r'https://[A-Za-z0-9.-]+(?::[0-9]{1,5})?/?', re.ASCII)
_SUPABASE_KEY_RE = re.compile(r'[\x21-\x7e]+', re.ASCII)


def supabase_config():
    """`(url, key)` проєкту Supabase простору ЛІГА з конфігу УСТАНОВКИ або `(None, None)` (4b-2: констант у коді нема).

    Джерела по черзі: корінь старого `tasks.json` (`supabase_url`, `supabase_key` — той самий файл, що несе
    `gitlab_ssh_key`), далі змінні оточення `SUPABASE_URL`/`SUPABASE_KEY`. Пара береться ЦІЛОЮ з одного джерела: адреса з
    файла й ключ з оточення не змішуються. Адреса — ПОВНІСТЮ `https://<хост>[:порт][/]` (хост — літери, цифри, `.`, `-`;
    без `/` в кінці в результаті), ключ — друковний ASCII без пробілів: так заготовка з документації
    (`https://<ref>.supabase.co`, `sb_publishable_…`) чи ключ із пробілом дають «конфігу нема» (`comments-unconfigured`), а не
    мережу з сміттям. Повну перевірку (DNS-імʼя, сервісний ключ) робить модуль `supabase-comments`. Кешу нема: файл маленький.
    Значень — ні в текстах, ні в журналах.

    ⛔ В ізольованому прогоні (`implicit.isolated()`: `DC_TASKS_FILE` чи `DC_NO_OVERVIEW`) джерело ОДНЕ — корінь файла задач:
    `SUPABASE_URL`/`SUPABASE_KEY` з оточення ігноруються. Причина: ізольований прогін — «стан не справжній цієї машини», а
    змінні оточення розробника несуть справжній проєкт ЛІГИ; тест чи демо під `DC_TASKS_FILE` не мусять мовчки дістати його.
    Під самим `DC_NO_OVERVIEW` (без `DC_TASKS_FILE`) «файл задач» — старий файл установки (`load_legacy_tasks`), як і раніше:
    відрізаються лише оточення й `pipeline-feedback`, читання файла не змінилось."""
    try:
        cfg = load_legacy_tasks()
    except (OSError, ValueError, RecursionError):      # надто глибока вкладеність JSON — не обвал, а «нема конфігу»
        cfg = None
    return supabase_from(cfg)


def supabase_from(cfg):
    """`(url, key)` за вже прочитаним коренем старого `tasks.json` (`cfg`; не словник — як порожній) — та сама логіка й ті самі
    джерела, що в `supabase_config()` (його тіло, винесене сюди без змін, щоб міграція ЛІГИ `liga_migrate.plan` брала облікові
    ТИМИ САМИМИ правилами, а не копією; ізоляція `implicit.isolated()` — як там)."""
    cfg = cfg if isinstance(cfg, dict) else {}
    sources = [(cfg.get('supabase_url'), cfg.get('supabase_key'))]
    if not implicit.isolated():                        # ⛔ в ізольованому прогоні оточення не читаємо (див. докстрінг)
        sources.append((os.environ.get('SUPABASE_URL'), os.environ.get('SUPABASE_KEY')))
    for url, key in sources:
        if not (isinstance(url, str) and isinstance(key, str)):
            continue
        url, key = url.strip(), key.strip()
        # адреса — повністю `https://<хост>[:порт][/]`; ключ — друковний ASCII без пробілів (див. докстрінг)
        if _SUPABASE_URL_RE.fullmatch(url) and _SUPABASE_KEY_RE.fullmatch(key):
            return url.rstrip('/'), key
    return None, None


def service_key_config():
    """`(url, key)` із оточення — `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` — або `(None, None)`: ЗАПАСНИЙ ключ ЛІГИ для CLI-пушера
    (`bin/overview_push.py`), коли `supabase_config()` конфігу не дав (спека 4c-1 §5; так було до 4c-1: сервісний ключ пушер
    брав з оточення). Та сама перевірка форми, що в `supabase_config`.

    ⛔ Це ОКРЕМА функція, а не четверте джерело `supabase_config()`: його читають і командні коментарі, і Teams, а сервісний
    ключ (повний доступ до проєкту) туди потрапляти не мусить. Лише пара — адреса з `SUPABASE_URL`, ключ з
    `SUPABASE_SERVICE_KEY`: так адреса з одного джерела й ключ з іншого не змішуються.

    ⛔ Той самий закон ізоляції, що в `supabase_config()`: в ізольованому прогоні (`implicit.isolated()`: `DC_TASKS_FILE` чи
    `DC_NO_OVERVIEW`) оточення НЕ читається. Корінь файла задач сервісного ключа не має (форми для нього нема, і заводити її
    не варто: це найпривілейованіший секрет ЛІГИ), тож у ізоляції результат завжди `(None, None)`. Інакше тест чи демо під
    `DC_TASKS_FILE` дістали б повний доступ до справжнього проєкту через `bin/overview_push.py` (`_legacy_config`). Поза
    ізоляцією поведінка 0.15.0 без змін."""
    if implicit.isolated():                            # ⛔ в ізольованому прогоні оточення не читаємо (див. докстрінг)
        return None, None
    url, key = os.environ.get('SUPABASE_URL'), os.environ.get('SUPABASE_SERVICE_KEY')
    if isinstance(url, str) and isinstance(key, str):
        url, key = url.strip(), key.strip()
        if _SUPABASE_URL_RE.fullmatch(url) and _SUPABASE_KEY_RE.fullmatch(key):
            return url.rstrip('/'), key
    return None, None


def jira_config():
    """`(base, email, token)` Jira простору ЛІГА з конфігу УСТАНОВКИ або `(None, None, None)` (4c-2: констант у коді нема).

    Адреса — `jira_base` у корені старого `tasks.json` (той самий файл, що несе `supabase_url`): ПОВНІСТЮ
    `https://<хост>[:порт][/]`, без `/` в кінці в результаті (форма — як у `supabase_config`: заготовка з документації
    `https://<сайт>.atlassian.net`, адреса з шляхом чи `user@` дають «конфігу нема», а не мережу з сміттям). Облікові — пара
    `JIRA_EMAIL`/`JIRA_TOKEN` з оточення, а коли її нема — файли `<HOME>/.claude/pipeline-feedback/jira-email|jira-token`
    (вміст `strip()`). Пошта й токен читаються НЕЗАЛЕЖНО, як в `_jira_creds` до 4c-2: кожне — значення з оточення, а коли воно
    порожнє чи негодне, — вміст файла; тож пошта з оточення й токен з файла поєднуються (це не пара Supabase). Пошта —
    непорожній друкований рядок, токен — друковний ASCII без пробілів. Значень — ні в текстах, ні в журналах; кешу нема: файли маленькі.

    ⛔ В ізольованому прогоні (`implicit.isolated()`: `DC_TASKS_FILE` чи `DC_NO_OVERVIEW`) і адреса, і облікові — ЛИШЕ з кореня
    файла задач: `jira_base`, `jira_email`, `jira_token` (два останні — нові необовʼязкові ключі для тестових фікстур; форма
    перевіряється так само, як у джерел оточення). Змінні `JIRA_*` і `<HOME>/.claude/pipeline-feedback/jira-*` НЕ читаються:
    інакше токен справжньої Jira розробника потрапляв би в тест чи демо. Без облікових у корені — `(None, None, None)`. Під
    самим `DC_NO_OVERVIEW` (без `DC_TASKS_FILE`) «корінь» — старий файл установки, як і раніше. Поза ізоляцією ключі
    `jira_email`/`jira_token` кореня ігноруються: поведінка 0.15.0 без змін.

    ⛔ Токен НІКОЛИ не в git/коді/чаті — лише локальний файл (chmod 600). Урок переїхав сюди з `bin/overview_push.py`
    (`_jira_creds`): у репозиторії живе лише адреса-заготовка, а справжні облікові — на машині людини."""
    try:
        cfg = load_legacy_tasks()
    except (OSError, ValueError, RecursionError):      # надто глибока вкладеність JSON — не обвал, а «нема конфігу»
        cfg = None
    return jira_from(cfg)


def jira_from(cfg):
    """`(base, email, token)` за вже прочитаним коренем старого `tasks.json` (`cfg`) — тіло `jira_config()`, винесене без змін
    (див. його докстрінг: джерела, порядок, ізоляція). Спільний помічник для `liga_migrate.plan`: ті самі правила, не копія."""
    base = cfg.get('jira_base') if isinstance(cfg, dict) else None
    if not isinstance(base, str):
        return None, None, None
    base = base.strip()
    if not _SUPABASE_URL_RE.fullmatch(base):           # та сама форма адреси, що в `supabase_config`
        return None, None, None

    def from_file(name):
        try:
            with open(os.path.expanduser('~/.claude/pipeline-feedback/' + name), encoding='utf-8') as f:
                return f.read()
        except (OSError, ValueError):
            return None
    def pick(env, name, key, valid):
        if implicit.isolated():                         # ⛔ лише корінь файла задач (ключ `jira_email`/`jira_token`)
            raw = cfg.get(key)
            return raw.strip() if isinstance(raw, str) and valid(raw.strip()) else None
        for raw in (os.environ.get(env), from_file(name)):          # оточення раніше за файл; порожнє/негодне — далі
            if isinstance(raw, str) and valid(raw.strip()):
                return raw.strip()
        return None
    email = pick('JIRA_EMAIL', 'jira-email', 'jira_email', lambda v: bool(v) and v.isprintable())
    token = pick('JIRA_TOKEN', 'jira-token', 'jira_token', lambda v: _SUPABASE_KEY_RE.fullmatch(v) is not None)
    return (base.rstrip('/'), email, token) if (email and token) else (None, None, None)
