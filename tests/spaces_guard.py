"""Охоронець СПРАВЖНЬОГО реєстру просторів для тестів, що пишуть простори.

Тест, який кличе `create_space`/`switch_space`/`load_registry` без власних тимчасових
`HOME`/`DEAI_HOME`, мовчки створив би чи змінив справжній `~/.deai/spaces.json` машини
дизайнера. Ізоляція в самих тестах — перша лінія; цей модуль — друга: знімок справжньої теки
реєстру перед модулем і звірка після. У знімку: чи існує сама тека («не було до → не зʼявилась
після»), ІМЕНА файлів у ній, md5 `spaces.json` і md5 `spaces.json.bak`. Вміст інших файлів теки не
читається: чужий файл помітний за зміною імен, а його правка на місці — ні.

Використання у файлі тестів:

    import spaces_guard
    _REAL = None
    def setUpModule():
        global _REAL
        _REAL = spaces_guard.snapshot()
    def tearDownModule():
        spaces_guard.assert_untouched(_REAL)

Справжня домівка береться з БАЗИ КОРИСТУВАЧІВ (`pwd`), а не з `$HOME`: тест, що підмінив `HOME`
(а так роблять усі тести просторів), не відводить охоронця від справжньої теки. Шлях
фіксується ПРИ ІМПОРТІ — до того, як будь-який тест підмінить оточення (`unittest discover`
імпортує всі модулі раніше, ніж запускає тести). Якщо в оточенні, з якого запущено прогін, уже
виставлено `DEAI_HOME`, стежимо й за ним.
"""
import hashlib
import os
import pwd

REAL_USER_HOME = pwd.getpwuid(os.getuid()).pw_dir


def _watched():
    homes = [os.path.join(REAL_USER_HOME, '.deai')]
    env = os.environ.get('DEAI_HOME')
    if env:
        if env == '~' or env.startswith('~/'):
            env = REAL_USER_HOME + env[1:]
        env = os.path.abspath(env)
        if env not in homes:
            homes.append(env)
    return tuple(homes)


#: Теки, за якими стежимо (справжня `~/.deai` + `DEAI_HOME` з оточення прогону, якщо він був).
WATCHED = _watched()
REAL_HOME = WATCHED[0]
REAL_REGISTRY = os.path.join(REAL_HOME, 'spaces.json')


def _md5(path):
    try:
        with open(path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    except OSError:
        return None


def snapshot(homes=None):
    """Стан теки реєстру: імена в ній (`None` — теки нема, тож поява самої теки — теж зміна),
    md5 `spaces.json` і `spaces.json.bak` (`None` — файла нема). `homes` — для самоперевірки охоронця; типово — справжні `WATCHED`."""
    out = {}
    for home in (WATCHED if homes is None else homes):
        try:
            names = sorted(os.listdir(home))
        except OSError:
            names = None                    # теки нема (чи не прочитати): «не існує» — теж стан
        out[home] = {'names': names,
                     'registry': _md5(os.path.join(home, 'spaces.json')),
                     'bak': _md5(os.path.join(home, 'spaces.json.bak'))}
    return out


def assert_untouched(before, homes=None):
    after = snapshot(homes)
    if after != before:
        raise AssertionError(
            f'тест зачепив СПРАВЖНІЙ реєстр просторів: було {before}, стало {after}')
