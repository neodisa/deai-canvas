"""Приклад модуля Deai Canvas: «Нотатки сторінок».

Показує все, що дає api 2: функції `tool_*` для панелі інструмента й функцію `action_*` для дії в ⌘K та меню задачі.
Сховище — один файл `notes.json` у `ctx["cache_dir"]`: `{id задачі: {id сторінки: текст}}`.
Лише стандартна бібліотека: модуль виконується ядром, а не імпортується.
"""
import json
import os
import tempfile
import threading

MAX_TEXT = 20000     # символів у одній нотатці
MAX_ID = 200         # довжина id задачі чи сторінки
_LOCK = threading.Lock()   # `tool_save` читає й пише файл: два виклики одночасно не мають губити один одного


def _file(ctx):
    """Шлях `notes.json`. Теку ядро не створює — це робить модуль (права лише для власника)."""
    os.makedirs(ctx["cache_dir"], mode=0o700, exist_ok=True)
    return os.path.join(ctx["cache_dir"], "notes.json")


def _read(path):
    """Усі нотатки. Нема файла чи він зіпсований — порожньо (приклад не лікує зіпсований файл)."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write(path, data):
    """Атомарно: тимчасовий файл у тій самій теці, потім `os.replace` — читач не побачить половину запису."""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".notes-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _ids(ctx, args):
    """`(task, page)` з аргументів панелі. Аргументи — чужий ввід: перевіряємо типи й довжину.
    id лишаються ключами словника й НІКОЛИ не потрапляють у шлях до файла."""
    if not isinstance(args, dict):
        raise ctx["ModuleError"]("bad-args", "args must be an object")
    task, page = args.get("task"), args.get("page")
    for v in (task, page):
        if not isinstance(v, str) or not 0 < len(v) <= MAX_ID:
            raise ctx["ModuleError"]("bad-args", "task and page must be non-empty strings")
    return task, page


def check(ctx):
    """Перевірка здоровʼя модуля: чи можна створити теку кешу."""
    try:
        os.makedirs(ctx["cache_dir"], mode=0o700, exist_ok=True)
    except OSError as e:
        return {"ok": False, "error": "cache-dir", "detail": str(e)[:200]}
    return {"ok": True}


def tool_load(ctx, args):
    """Панель: `deai.call("tool_load", {task, page})` → `{"text": "…"}`."""
    task, page = _ids(ctx, args)
    notes = _read(_file(ctx))
    by_page = notes.get(task)
    text = by_page.get(page, "") if isinstance(by_page, dict) else ""
    return {"text": text if isinstance(text, str) else ""}


def tool_save(ctx, args):
    """Панель: `deai.call("tool_save", {task, page, text})`. Порожній текст видаляє нотатку."""
    task, page = _ids(ctx, args)
    text = args.get("text")
    if not isinstance(text, str) or len(text) > MAX_TEXT:
        raise ctx["ModuleError"]("bad-args", "text must be a string of at most %d characters" % MAX_TEXT)
    path = _file(ctx)
    with _LOCK:
        notes = _read(path)
        by_page = notes.get(task)
        if not isinstance(by_page, dict):
            by_page = notes[task] = {}
        if text:
            by_page[page] = text
        else:
            by_page.pop(page, None)
        if not by_page:
            notes.pop(task, None)
        _write(path, notes)
    return {"ok": True}


def action_summary(ctx, target):
    """Дія «Нотатки задачі» (⌘K, меню задачі): тост із кількістю нотаток задачі.
    `target = {"from", "task": {"id", "name", "dir"}, "iteration": …}`; результат — `{"ok", "text"?, "url"?}`."""
    by_page = _read(_file(ctx)).get(target["task"]["id"])
    n = sum(1 for v in by_page.values() if isinstance(v, str) and v.strip()) if isinstance(by_page, dict) else 0
    return {"ok": True, "text": f"Нотаток: {n}"}
