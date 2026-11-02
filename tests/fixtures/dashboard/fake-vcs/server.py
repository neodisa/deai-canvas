"""Тестовий модуль ролі `vcs` для живого тесту 4c-1 (`tests/live/dashboard-role.test.mjs`): БЕЗ git і БЕЗ мережі. Потрібен лише
для одного: `POST /api/vcs-push` у звичайному просторі — єдиний серверний тригер синку дашборда, і справжній `git-sync` ходив би
на сервер. `push` каже «відправлено» (`synced: true`) і нічого не робить."""


def check(ctx):
    return {'ok': True, 'detail': 'fake vcs ok'}


def status(ctx, target):
    return {'behind': 0, 'behind_path': 0, 'unpushed': 0, 'on_remote': True, 'web': None, 'label': 'Fake'}


def push(ctx, target, src, meta):
    return {'ok': True, 'synced': True, 'sha': '0123abc'}


def pull(ctx, target, dst, opts=None):
    return {'ok': True, 'pulled': False}


def validate(ctx, target):
    return {'ok': True}


def mirror_dir(ctx, target):
    return '/nonexistent/fake-vcs-mirror'
