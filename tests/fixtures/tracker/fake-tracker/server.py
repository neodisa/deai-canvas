"""Тестовий модуль ролі `tracker` для живих тестів 4c-2: БЕЗ мережі. Статуси віддає з JSON-файла (`settings.statuses_file`,
форма `{ключ: {name, cat}}`), а кожен виклик дописує рядком JSON у `settings.log_file` (за ним тест бачить, ЯКІ ключі ядро
реально віддало модулю). Коли у файлі `{"error": "…"}`, `statuses` відмовляє цим текстом (збій трекера → банер на екрані «Задачі»).
Файл перечитується на кожен виклик: тест міняє його між запитами, не перезапускаючи сервер."""
import json


def _log(ctx, **entry):
    path = ctx['settings'].get('log_file')
    if path:
        with open(path, 'a', encoding='utf-8') as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + '\n')


def check(ctx):
    return {'ok': True, 'detail': 'fake tracker ok'}


def statuses(ctx, keys):
    _log(ctx, fn='statuses', keys=list(keys))
    with open(ctx['settings']['statuses_file'], encoding='utf-8') as fh:
        data = json.load(fh)
    if isinstance(data, dict) and isinstance(data.get('error'), str):
        raise ctx['ModuleError']('tracker-error', message=data['error'])
    return data
