"""Старий файл задач ЛІГИ й форма облікових, яку знає міграція (етап 4c-1; з 4d-4b — без читачів оригіналів).

Читачі `supabase_config`/`jira_config`/`service_key_config` (корінь файла, оточення, `~/.claude/pipeline-feedback/`) ВИДАЛЕНО: після кроку
`liga-4d4b` облікові лежать у явних записах `space.json` і `secrets.json`, а рантайм оригіналів не читає (охоронець `tests/test_no_originals.py`).
Лишилось: шлях і читання старого файла (його потребують міграція, `ops/`, `bin/roots.py`), кошик Storage ЛІГИ й регекспи ФОРМИ (їх потребує
`liga_migrate`: він один іще знає, як читалися оригінали).
"""
import json
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


#: Кошик Storage ЛІГИ для скріншотів пінів: картка Teams бере `meta.shotUrl` звідти (як старий адаптер 0.9.0). Джерело правди —
#: тут (4d-3b): його потребує й міграція ЛІГИ (`liga_migrate`), яка не імпортує `serve`; `serve.LEGACY_SHOTS_BUCKET` — аліас.
LEGACY_SHOTS_BUCKET = 'overview-thumbs'

_SUPABASE_URL_RE = re.compile(r'https://[A-Za-z0-9.-]+(?::[0-9]{1,5})?/?', re.ASCII)
_SUPABASE_KEY_RE = re.compile(r'[\x21-\x7e]+', re.ASCII)
