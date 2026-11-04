"""Тестовий модуль ролі `notify` для живих тестів 4c-3: БЕЗ мережі й Supabase. Стан тиші — JSON-файл (`settings.state_file`,
форма `{канал: {muted_at, muted_by}}`); `mute_set` пише в нього, `mute_state` читає. Коли у файлі `{"error": "…"}`, обидві
функції (і `check`) відмовляють цим текстом (режим «збій»: пункт «Сповіщати Teams» мусить стати «стан невідомий», а не «увімкнено»).
Файл перечитується на кожен виклик: тест міняє його між запитами, не перезапускаючи сервер. Рядки віддаються у формі справжнього
модуля (`project_id`, `muted_at`, `muted_by`)."""
import json
import os


def _load(ctx):
    path = ctx['settings']['state_file']
    if not os.path.exists(path):
        return {}
    with open(path, encoding='utf-8') as fh:
        data = json.load(fh)
    if isinstance(data, dict) and isinstance(data.get('error'), str):
        raise ctx['ModuleError']('notify-error', message=data['error'])
    return data


def check(ctx):
    _load(ctx)
    return {'ok': True, 'detail': 'fake notify ok'}


def mute_state(ctx):
    return [{'project_id': ch, 'muted_at': v.get('muted_at'), 'muted_by': v.get('muted_by', '')}
            for ch, v in sorted(_load(ctx).items())]


def mute_set(ctx, channel, muted, by):
    db = _load(ctx)
    if muted:
        db[channel] = {'muted_at': '2026-11-01T10:00:00', 'muted_by': by}
    else:
        db.pop(channel, None)
    with open(ctx['settings']['state_file'], 'w', encoding='utf-8') as fh:
        json.dump(db, fh)
    return muted
