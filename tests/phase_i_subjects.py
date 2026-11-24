"""Фаза И: темі git-комітів змінилися, а знімки `tests/fixtures/*/before-*.json` ЗАМОРОЖЕНІ («еталон не перезаписувати»).

`amend_subjects(obj)` — одна точка, де старі теми з знімка перекладаються на теми фази И; сам знімок лишається байт-у-байт:
  * `publish: N iteration(s)` → `publish: N iteration(s) · it1 … itN`. Знімки знято на стенді, де опубліковані рівно `it1 … itN`
    (N = 2 скрізь), тож id відновлюються однозначно;
  * `itN: автосинк (<інструмент>)` — без перекладу: з 24.11.2026 крок 2 автосинку знову комітить без трейлера (спека
    Stop-хука, розділ 5), як у знімках.
Знімки знято через `serve.autosync()` напряму, а не через маршрут, тож коміту `itN: зміни AI` (його робить лише маршрут
`/api/autosync`) у них немає і додавати його нема куди.
Переклад РЕКУРСИВНИЙ і лише за точним збігом усього рядка: решта знімка не чіпається.
"""
import re

_PUBLISH = re.compile(r'^publish: (\d+) iteration\(s\)$')


def amend_subject(text):
    m = _PUBLISH.match(text)
    if m:
        return f'{text} · ' + ' '.join(f'it{i}' for i in range(1, int(m.group(1)) + 1))
    return text


def amend_subjects(obj):
    if isinstance(obj, str):
        return amend_subject(obj)
    if isinstance(obj, list):
        return [amend_subjects(x) for x in obj]
    if isinstance(obj, dict):
        return {k: amend_subjects(v) for k, v in obj.items()}
    return obj
