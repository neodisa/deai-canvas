"""Прогрес зʼємки: розбір подій із stderr дитини й накопичення стану.

Чистий модуль — ні HTTP, ні процесів, ні потоків. Друга половина контракту
живе в `bin/shots-progress.mjs` (там ПИШУТЬ), і константу маркера звіряє
окремий тест: розійдуться два боки — прогрес замовкне правдоподібно, тобто
зʼємка йтиме, а лічильник стоятиме на нулі.
"""
import json

MARK = '@shot '


def parse_progress_line(line):
    """Рядок stderr → подія (dict) або None.

    None означає «це не наша подія» — і такий рядок мусить лишитись текстом
    причини для дизайнера. Саме там приходить справжня біда (не встановлений
    chromium), тому глушити нерозпізнане не можна.
    """
    if not line.startswith(MARK):
        return None
    try:
        ev = json.loads(line[len(MARK):])
    except (json.JSONDecodeError, ValueError):
        # Обрізаний рядок — звичайна річ, коли процес убили посеред запису
        return None
    if not isinstance(ev, dict) or not ev.get('ev'):
        return None
    return ev


class ShootProgress:
    """Стан ОДНІЄЇ зʼємки. Живе в памʼяті серверного процесу."""

    def __init__(self):
        self.running = True
        self.total = None
        self.done = 0
        self.current = None
        # ПЕРЕЛІК, а не останній кадр: опитування клієнта може пропустити такт
        # (вкладка в фоні дроселює таймери), і тоді кадр між тактами зник би з
        # полотна до кінця прогону.
        self.frames = []
        self.failed = []
        self.stopped = False

    def apply(self, ev):
        kind = ev.get('ev')
        if kind == 'start':
            self.total = ev.get('total')
        elif kind == 'frame':
            self.done += 1
            self.current = ev.get('key')
            self.frames.append({'key': ev.get('key'), 'sha': ev.get('sha'),
                                'stamp': ev.get('stamp'), 'capturedAt': ev.get('capturedAt'),
                                'w': ev.get('w'), 'h': ev.get('h')})
        elif kind == 'fail':
            self.done += 1
            self.current = ev.get('key')
            self.failed.append({'key': ev.get('key'), 'problem': ev.get('problem')})
        elif kind == 'done':
            self.running = False
        # Невідома подія ігнорується свідомо: новіший shoot.mjs поруч зі старим
        # сервером не сміє валити прогрес — гірше за відсутність нової події
        # лише падіння на ній.

    def finish(self, stopped=False):
        """Процес завершився. Кличеться ЗАВЖДИ, і саме тому `running` чесний:
        події `done` не буде ніколи, якщо дитину вбили."""
        self.running = False
        self.stopped = self.stopped or stopped

    def snapshot(self):
        return {'running': self.running, 'total': self.total, 'done': self.done,
                'current': self.current, 'frames': list(self.frames),
                'failed': list(self.failed), 'stopped': self.stopped}
