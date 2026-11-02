"""Тестовий модуль ролі `dashboard` для живих тестів 4c-1: БЕЗ мережі. Рядки команди віддає з JSON-файла
(`settings.rows_file`), а кожен виклик дописує рядком JSON у `settings.log_file` (за ним тест бачить, ЧИЇМИ руками ядро
читало й писало). `settings.fail` — текст, яким `rows` відмовляє (збій модуля → плашка на екрані «Задачі»)."""
import json


def _log(ctx, **entry):
    path = ctx['settings'].get('log_file')
    if path:
        with open(path, 'a', encoding='utf-8') as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + '\n')


def check(ctx):
    return {'ok': True, 'detail': 'fake dashboard ok'}


def rows(ctx):
    _log(ctx, fn='rows')
    fail = ctx['settings'].get('fail')
    if fail:
        raise ctx['ModuleError']('dashboard-error', message=fail)
    with open(ctx['settings']['rows_file'], encoding='utf-8') as fh:
        return json.load(fh)


def push(ctx, cards, mode):
    _log(ctx, fn='push', mode=mode, ids=[c.get('id') for c in cards])
    return {'ok': len(cards), 'failed': {}}


def open_comments(ctx):
    _log(ctx, fn='open_comments')
    return {}
