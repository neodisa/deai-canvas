"""Вигадана пара «адреса + ключ» Supabase простору ЛІГА для тестів (4b-2: констант у `serve.py` більше нема).

Тести, що проходять шляхом ЛІГИ, кладуть її в оточення (`SUPABASE_URL`/`SUPABASE_KEY` — законне джерело
`serve.supabase_config()`) разом зі своїми тимчасовими `HOME`/`DEAI_HOME`/`DC_TASKS_FILE`: справжній `tasks.json`
установки не читається, а справжні адреса й ключ у репозиторії не живуть. Мережі це не відкриває: `urlopen` у цих тестах
підмінено записувачем чи розтяжкою.
"""
SB_URL = 'https://demo.supabase.co'
SB_KEY = 'sb_publishable_test'
ENV = {'SUPABASE_URL': SB_URL, 'SUPABASE_KEY': SB_KEY}


def _ensure_builtin():
    """Вбудований `supabase-comments` у каталозі тесту. Тести на `tests/test_modules.py::Env` підміняють `builtin_dir()` на
    порожню тимчасову теку (щоб рахувати лише свої фікстури); шлях ЛІГИ ж іде ВБУДОВАНИМ модулем (`serve.comments_route`),
    тож без нього в каталозі він мовчки відмовив би («module is not loaded»). Копіюємо справжній модуль у ту теку (раз);
    коли `builtin_dir()` — справжня `app/modules`, нічого не робимо."""
    import os
    import shutil
    import deai_modules
    real = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app', 'modules', 'supabase-comments')
    dest = os.path.join(deai_modules.builtin_dir(), 'supabase-comments')
    if not os.path.isdir(dest):
        shutil.copytree(real, dest, ignore=shutil.ignore_patterns('__pycache__'))
        deai_modules.reset_caches()


def patch_open(test, fn):
    """Підставити `fn(req, timeout)` замість шва `_open` вбудованого модуля `supabase-comments` на час тесту `test`.

    З 4b-2 командні коментарі ЛІГИ ходять тим самим модулем, що й у звичайних просторів, а модуль не кличе
    `urllib.request.urlopen` — його запит іде лише крізь `_open` (див. `tests/test_supabase_comments.py`). Тож тести, що
    колись підміняли `urlopen` для шляху ЛІГИ (`supabase_pins`/`patch_project_pin`), підміняють цей шов: `fn` бачить той
    самий `Request` (повний `https://`-URL, метод, заголовки, тіло) і повертає відповідь, придатну для `with … as resp`
    (`resp.status`, `resp.read(limit)`). Справжньої мережі нема: без підміни модуль пішов би в `https://demo.supabase.co`."""
    from unittest import mock
    import deai_modules
    _ensure_builtin()
    g = deai_modules.catalog()['supabase-comments'].fn('check').__globals__
    patcher = mock.patch.dict(g, {'_open': fn})
    patcher.start()
    test.addCleanup(patcher.stop)
    return g


class Resp:
    """Відповідь шва `_open` для `with … as resp`: `status` і `read(limit)`."""

    def __init__(self, body=b'[]', status=200):
        self._body, self.status = body, status

    def read(self, *limit):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def empty_open(req, timeout=None):
    """Шов `_open`, що віддає «коментарів нема» (`[]`) на будь-який запит: заміна колишньої підміни
    `supabase_pins = lambda project: []` у тестах, яким командні піни не потрібні, а мережі не можна."""
    return Resp(b'[]')
