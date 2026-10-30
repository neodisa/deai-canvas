"""Вигадана пара «адреса + ключ» Supabase простору ЛІГА для тестів (4b-2: констант у `serve.py` більше нема).

Тести, що проходять шляхом ЛІГИ, кладуть її в оточення (`SUPABASE_URL`/`SUPABASE_KEY` — законне джерело
`serve.supabase_config()`) разом зі своїми тимчасовими `HOME`/`DEAI_HOME`/`DC_TASKS_FILE`: справжній `tasks.json`
установки не читається, а справжні адреса й ключ у репозиторії не живуть. Мережі це не відкриває: `urlopen` у цих тестах
підмінено записувачем чи розтяжкою.
"""
SB_URL = 'https://demo.supabase.co'
SB_KEY = 'sb_publishable_test'
ENV = {'SUPABASE_URL': SB_URL, 'SUPABASE_KEY': SB_KEY}
