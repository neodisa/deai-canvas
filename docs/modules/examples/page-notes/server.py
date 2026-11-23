"""Example Deai Canvas module: «Page notes» (Нотатки сторінок).

Shows what api 2 gives: `tool_*` functions for the panel of a tool and an `action_*` function for an action in ⌘K and the
task menu. Storage is one file, `notes.json`, in `ctx["cache_dir"]`: `{task id: {page id: text}}`.
Standard library only: the core executes the module, it is not imported.
"""
import json
import os
import tempfile
import threading

MAX_TEXT = 20000     # characters in one note
MAX_ID = 200         # length of a task or page id
_LOCK = threading.Lock()   # `tool_save` reads and writes the file: two simultaneous calls must not lose each other


def _file(ctx):
    """Path of `notes.json`. The core does not create the folder — the module does (owner-only access)."""
    os.makedirs(ctx["cache_dir"], mode=0o700, exist_ok=True)
    return os.path.join(ctx["cache_dir"], "notes.json")


def _read(path):
    """All notes. No file or a corrupt one means empty (the example does not repair a corrupt file)."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write(path, data):
    """Atomically: a temporary file in the same folder, then `os.replace` — a reader never sees half a write."""
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
    """`(task, page)` from the panel's arguments. Arguments are foreign input: check types and length.
    The ids stay dictionary keys and NEVER become part of a file path.
    A failure is raised as `module-error`: that is the code the panel sees from `deai.call` (a code of our own that Deai does
    not know would be turned into it anyway), so the example says it straight."""
    if not isinstance(args, dict):
        raise ctx["ModuleError"]("module-error", "args must be an object")
    task, page = args.get("task"), args.get("page")
    for v in (task, page):
        if not isinstance(v, str) or not 0 < len(v) <= MAX_ID:
            raise ctx["ModuleError"]("module-error", "task and page must be non-empty strings")
    return task, page


def check(ctx):
    """Health check of the module: can the cache folder be created."""
    try:
        os.makedirs(ctx["cache_dir"], mode=0o700, exist_ok=True)
    except OSError as e:
        return {"ok": False, "error": "cache-dir", "detail": str(e)[:200]}
    return {"ok": True}


def tool_load(ctx, args):
    """Panel: `deai.call("tool_load", {task, page})` -> `{"text": "…"}`."""
    task, page = _ids(ctx, args)
    notes = _read(_file(ctx))
    by_page = notes.get(task)
    text = by_page.get(page, "") if isinstance(by_page, dict) else ""
    return {"text": text if isinstance(text, str) else ""}


def tool_save(ctx, args):
    """Panel: `deai.call("tool_save", {task, page, text})`. An empty text deletes the note."""
    task, page = _ids(ctx, args)
    text = args.get("text")
    if not isinstance(text, str) or len(text) > MAX_TEXT:
        raise ctx["ModuleError"]("module-error", "text must be a string of at most %d characters" % MAX_TEXT)
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
    """Action «Нотатки задачі» (⌘K, task menu): a toast with the number of the task's notes.
    `target = {"from", "task": {"id", "name", "dir"}, "iteration": …}`; the result is `{"ok", "text"?, "url"?}`."""
    by_page = _read(_file(ctx)).get(target["task"]["id"])
    n = sum(1 for v in by_page.values() if isinstance(v, str) and v.strip()) if isinstance(by_page, dict) else 0
    return {"ok": True, "text": f"Нотаток: {n}"}
