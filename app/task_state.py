"""Легкий стан задачі з `<dir>/iterations.json` — ОДНЕ місце для пушера реєстру
(`bin/overview_push.py`) і сервера (екран «Задачі», `app/serve.py`).

Жив у `overview_push.py`; переїхав сюди, щоб сервер не копіював логіку: дві копії
розʼїхались би, і дизайнер бачив би на екрані одне, а в овервью — інше.
Імпортувати `overview_push` із сервера не можна (тягне мережу й Supabase), а ця
функція — чиста й офлайнова.
"""
import json
import os
import re


def iter_count(its):
    """Кількість ітерацій = найбільший порядковий номер id «itN» (канвас може
    зберігати лише останню ітерацію у списку), інакше — довжина списку."""
    nums = [int(m.group(1)) for i in its
            for m in [re.match(r"it(\d+)$", str(i.get("id", "")))] if m]
    return max(nums) if nums else len(its)


def task_state(task):
    """Легкий стан задачі для build_row() з <dir>/iterations.json (джерело істини
    канвасу: список ітерацій + publish_url). Захищено — ніколи не кидає виняток;
    немає файлу/директорії → нулі/False. code_url = реальний Vercel publish_url
    (НЕ localhost `live`), і лише якщо опубліковано."""
    d = task.get("dir") if isinstance(task, dict) else None
    d = d if isinstance(d, str) else ""
    task = task if isinstance(task, dict) else {}
    meta = {}
    # ⛔ Порожній dir — НЕ читаємо: os.path.join("", "iterations.json") це файл у
    # cwd процесу, і сервер показав би чужий iterations.json як стан цієї задачі.
    if d:
        try:
            with open(os.path.join(d, "iterations.json"), encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, ValueError):
            meta = {}
    # ⛔ Валідний JSON не тієї форми (файл правили руками) — теж «нема даних»:
    # сервер кличе це на кожен запит екрана «Задачі», виняток = 500 на весь екран.
    if not isinstance(meta, dict):
        meta = {}
    its = meta.get("iterations")
    its = [i for i in its if isinstance(i, dict)] if isinstance(its, list) else []
    publish_url = meta.get("publish_url")
    published = bool(publish_url) or any(i.get("published") for i in its)
    # реальна дата останнього апдейту прев'ю: published_at, інакше дата останньої ітерації
    iter_dates = [i.get("date") for i in its if i.get("date")]
    last_update = meta.get("published_at") or (iter_dates[-1] if iter_dates else None)
    gl = meta.get("gitlab")
    gl = gl if isinstance(gl, dict) else {}
    # к-сть відкриваних сторінок опублікованої (фолбек — останньої) ітерації.
    # Повністю захищено: будь-яка проблема (нема моделі/теки/pages.json) → 0, ніколи не ламає sync.
    pages_n = 0
    try:
        import pages_model as _pm
        _pub = next((i for i in reversed(its) if i.get("published")), its[-1] if its else None)
        if _pub:
            _idir = os.path.join(d, "iterations", _pub["id"])
            pages_n = len(_pm.openable_pages(_pm.read_pages(_idir)))
    except Exception:  # noqa: BLE001
        pages_n = 0
    return {
        "iterations": iter_count(its),
        "pages": pages_n,
        "published": published,
        "finalized": False,  # TODO(integration): реального сигналу фіналізації ще нема
        "open_comments": 0,  # TODO(integration): реальні лічильники з comment_channel
        "figma": task.get("figma"),
        "code_url": publish_url if published else None,
        "last_update": last_update,
        "backup_at": gl.get("synced_at"),  # час останнього gitlab-sync = «бекап»
        # id останньої ітерації; .get, а не ["id"]: ітерація без id (iter_count її
        # переживає) інакше зламала б пуш реєстру KeyError-ом
        "last_iter": its[-1].get("id") if its else None,
        "dir_exists": os.path.isdir(d),  # тека задачі на диску є (екран «Задачі» не бреше про знесене)
    }
