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
