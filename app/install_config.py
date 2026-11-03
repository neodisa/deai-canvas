"""Конфіг УСТАНОВКИ (етап 4c-1): старий файл задач ЛІГИ й адреса/ключ Supabase з нього.

Жив у `serve.py`; переїхав сюди, щоб ядро дашборда (`app/dashboard.py`) і CLI-пушер (`bin/overview_push.py`) читали той самий
конфіг БЕЗ імпорту `serve` (він тягне сервер, мережу й увесь стан). `serve` реекспортує імена: інструменти (`ops/`, `bin/`)
і тести беруть їх звідти, а `serve.supabase_config` лишається тонкою обгорткою — точкою підміни для тестів.
"""
import json
import os
import re

import spaces  # простори машини: де лежить старий файл задач (`spaces.legacy_tasks_file`)


def legacy_tasks_path():
    """Старий файл задач (простір `legacy`) — для інструментів ЛІГА (доктор, `roots.py`,
    `ops/reseal_gate.py`): вони працюють із ним, у який би простір не дивився запит."""
    return spaces.legacy_tasks_file()


def load_legacy_tasks():
    """Старий файл як є; нема — `FileNotFoundError`, як `load_tasks` до просторів."""
    with open(legacy_tasks_path(), encoding='utf-8') as f:
        return json.load(f)


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
    Значень — ні в текстах, ні в журналах."""
    try:
        cfg = load_legacy_tasks()
    except (OSError, ValueError, RecursionError):      # надто глибока вкладеність JSON — не обвал, а «нема конфігу»
        cfg = None
    cfg = cfg if isinstance(cfg, dict) else {}
    for url, key in ((cfg.get('supabase_url'), cfg.get('supabase_key')),
                     (os.environ.get('SUPABASE_URL'), os.environ.get('SUPABASE_KEY'))):
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
    `SUPABASE_SERVICE_KEY`: так адреса з одного джерела й ключ з іншого не змішуються."""
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
    (вміст `strip()`). Оточення раніше за файли; пара береться ЦІЛОЮ з одного джерела: пошта з оточення й токен з файла не
    змішуються. Токен — друковний ASCII без пробілів. Значень — ні в текстах, ні в журналах; кешу нема: файли маленькі.

    ⛔ Токен НІКОЛИ не в git/коді/чаті — лише локальний файл (chmod 600). Урок переїхав сюди з `bin/overview_push.py`
    (`_jira_creds`): у репозиторії живе лише адреса-заготовка, а справжні облікові — на машині людини."""
    try:
        cfg = load_legacy_tasks()
    except (OSError, ValueError, RecursionError):      # надто глибока вкладеність JSON — не обвал, а «нема конфігу»
        cfg = None
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
    for email, token in ((os.environ.get('JIRA_EMAIL'), os.environ.get('JIRA_TOKEN')),
                         (from_file('jira-email'), from_file('jira-token'))):
        if not (isinstance(email, str) and isinstance(token, str)):
            continue
        email, token = email.strip(), token.strip()
        if email and email.isprintable() and _SUPABASE_KEY_RE.fullmatch(token):
            return base.rstrip('/'), email, token
    return None, None, None
