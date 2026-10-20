"""Тестовий модуль ролі `publish` для живого тесту екрана «Підключення»: перевірка ЛОКАЛЬНА (жодної мережі),
секрет у відповідь не потрапляє. Публікувати живий тест не публікує — `publish` лише відмовляє."""


def check(ctx):
    note = ctx['settings'].get('note', '')
    if note == 'fail':
        return {'ok': False, 'error': 'memo-says-no', 'detail': 'note is fail'}
    return {'ok': True, 'detail': 'memo ok'}


def publish(ctx, built, *args, **kwargs):
    raise ctx['ModuleError']('module-error', message='memo-publish does not publish')
