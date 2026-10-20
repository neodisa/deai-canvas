"""Другий тестовий модуль ролі `publish` (копія `memo-publish` з іншими id і назвою): потрібен живим тестам, де роль
«займає» ще хтось, поки людина вирішує, чи замінювати перший постачальник (свіжа згода на заміну). Перевірка ЛОКАЛЬНА
(жодної мережі), секрет у відповідь не потрапляє, публікувати нічого не публікує."""


def check(ctx):
    note = ctx['settings'].get('note', '')
    if note == 'fail':
        return {'ok': False, 'error': 'memo-says-no', 'detail': 'note is fail'}
    return {'ok': True, 'detail': 'memo ok'}


def publish(ctx, built, *args, **kwargs):
    raise ctx['ModuleError']('module-error', message='memo-publish2 does not publish')
