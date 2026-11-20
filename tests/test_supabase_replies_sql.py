"""Статична перевірка SQL таблиці `comment_replies` модуля `supabase-comments` (`replies.sql` і блок у `schema.sql`).

⛔ SQL тут НІКУДИ не виконується: локального Postgres нема, а на справжній проєкт Supabase скрипт виконує людина сама, після явного
«так». Тест лише читає два файли як текст (stdlib) і звіряє їх із тим, що спека (§1) велить мати в таблиці, правах, тригерах.

Терміни.
  * ШАПКА `replies.sql` — провідні рядки-коментарі (`--`) і порожні рядки до першого рядка SQL (`create table …`);
  * БЛОК — усе від першого рядка SQL до кінця файла; рівно його `schema.sql` тримає між рядками `-- >>> replies` і `-- <<< replies`.
Порівняння блоку з файлом нормалізує лише пробіли наприкінці рядків і кінцеві порожні рядки.
"""
import os
import re
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
MODULE_DIR = os.path.join(os.path.dirname(_HERE), 'app', 'modules', 'supabase-comments')
BEGIN, END = '-- >>> replies', '-- <<< replies'


def _read(name):
    with open(os.path.join(MODULE_DIR, name), encoding='utf-8') as f:
        return f.read()


def _norm(text):
    return '\n'.join(ln.rstrip() for ln in text.strip('\n').splitlines()).rstrip()


def split_header(text):
    """`(шапка, блок)`: шапка — провідні рядки `--` і порожні; блок — решта."""
    lines = text.splitlines()
    n = 0
    while n < len(lines) and (not lines[n].strip() or lines[n].lstrip().startswith('--')):
        n += 1
    return '\n'.join(lines[:n]), '\n'.join(lines[n:])


def marked_block(schema):
    lines = schema.splitlines()
    begins = [i for i, ln in enumerate(lines) if ln == BEGIN]
    ends = [i for i, ln in enumerate(lines) if ln == END]
    assert len(begins) == 1 and len(ends) == 1 and begins[0] < ends[0], 'у schema.sql має бути рівно одна пара маркерів'
    return '\n'.join(lines[begins[0] + 1:ends[0]])


def code_only(sql):
    """SQL без рядків-коментарів і без `--` у кінці рядків."""
    return '\n'.join(re.sub(r'--.*$', '', ln) for ln in sql.splitlines())


def check_sql(case, sql, where):
    """Усі вимоги до тексту SQL таблиці відповідей; викликається і для `replies.sql`, і для блоку зі `schema.sql`."""
    low = code_only(sql).lower()
    T = 'public.comment_replies'
    case.assertRegex(low, r'create table if not exists public\.comment_replies \(', where)
    case.assertRegex(low, r'create index if not exists comment_replies_project_idx on public\.comment_replies\(project_id\)', where)
    case.assertIn(f'alter table {T} enable row level security;', low, where)
    for p, rule in (('read', 'for select using (true)'), ('insert', 'for insert with check (true)'),
                    ('update', 'for update using (true) with check (true)'), ('delete', 'for delete using (true)')):
        drop = re.search(rf'drop policy if exists clr_{p}\s+on {re.escape(T)};', low)
        create = re.search(rf'create policy clr_{p}\s+on {re.escape(T)} {re.escape(rule)};', low)
        case.assertTrue(drop and create, f'{where}: політика clr_{p}')
        case.assertLess(drop.start(), create.start(), f'{where}: drop policy ПЕРЕД create policy clr_{p}')
        case.assertEqual(len(re.findall(rf'create policy clr_{p}\b', low)), 1, where)
    case.assertEqual(len(re.findall(r'create policy', low)), 4, where)
    grant = f'grant select, insert, update, delete on {T} to anon, authenticated;'
    revoke = f'revoke truncate, references, trigger on {T} from anon, authenticated;'
    case.assertIn(grant, low, where)
    case.assertIn(revoke, low, where)
    case.assertLess(low.index(grant), low.index(revoke), f'{where}: спершу права, потім відібрані зайві')
    for fn in ('clr_project_id_immutable', 'clr_delete_scope_guard'):
        m = re.search(rf'create or replace function public\.{fn}\(\) returns trigger\s+language plpgsql set search_path = pg_catalog, public as \$\$',
                      low)
        case.assertIsNotNone(m, f'{where}: функція {fn} із фіксованим search_path')
    case.assertIn("row_security_active('public.comment_replies')", low, where)
    case.assertEqual(low.count("row_security_active('public.comment_replies')"), 2, where)  # по одному в кожній функції
    case.assertRegex(low, r'if n > 100 then', where)
    case.assertNotRegex(low, r'if n > (?!100\b)\d+', where)
    case.assertRegex(low, r'count\(distinct project_id\) into n, p from removed', where)
    case.assertRegex(low, r'if p > 1 then', where)
    case.assertRegex(low, rf'create trigger clr_project_id_immutable before update on {re.escape(T)}\s+for each row execute function public\.clr_project_id_immutable\(\);', where)
    case.assertRegex(low, rf'create trigger clr_delete_scope_guard after delete on {re.escape(T)}\s+referencing old table as removed\s+for each statement execute function public\.clr_delete_scope_guard\(\);', where)
    for trg in ('clr_project_id_immutable', 'clr_delete_scope_guard'):
        d, c = low.find(f'drop trigger if exists {trg} on {T};'), low.find(f'create trigger {trg} ')
        case.assertTrue(d >= 0 and c >= 0, f'{where}: drop trigger if exists і create trigger {trg}')
        case.assertLess(d, c, f'{where}: drop trigger if exists ПЕРЕД create trigger {trg}')
    case.assertEqual(len(re.findall(r'create trigger', low)), 2, where)
    m = re.search(r'do \$\$\s*begin\s*(.*?)\s*exception when duplicate_object then\s*null;\s*end \$\$;', low, re.S)
    case.assertIsNotNone(m, f'{where}: блок do $$ … exception when duplicate_object')
    case.assertEqual(m.group(1).strip(), f'alter publication supabase_realtime add table {T};', where)
    # Жодного зовнішнього ключа чи каскаду (спека §1): старі клієнти видаляють лише рядок `comments`. Єдиний дозволений збіг зі словом
    # `references` — привілей у `revoke`, тож цей рядок із перевірки прибрано.
    low_no_revoke = low.replace(revoke, '')
    for bad in (r'\breferences\b', r'foreign\s+key', r'cascade'):
        case.assertIsNone(re.search(bad, low_no_revoke), f'{where}: заборонено {bad}')
    # Лише таблиця відповідей: `comments` у цьому скрипті не чіпається (у спільній базі його політики можуть бути іншими).
    case.assertNotRegex(low, r'public\.comments\b', where)


class RepliesSqlTest(unittest.TestCase):
    def test_the_replies_file_satisfies_the_spec(self):
        check_sql(self, split_header(_read('replies.sql'))[1], 'replies.sql')

    def test_the_block_in_schema_satisfies_the_spec_too(self):
        check_sql(self, marked_block(_read('schema.sql')), 'schema.sql')

    def test_the_block_in_schema_equals_the_replies_file_without_its_header(self):
        header, block = split_header(_read('replies.sql'))
        self.assertTrue(block.lstrip().startswith('create table if not exists public.comment_replies'),
                        'шапка закінчується перед `create table`')
        self.assertTrue(header.strip(), 'шапка непорожня')
        self.assertEqual(_norm(marked_block(_read('schema.sql'))), _norm(block))

    def test_the_markers_sit_at_the_end_of_schema_and_alone_on_their_lines(self):
        text = _read('schema.sql')
        self.assertEqual(text.count(BEGIN), 1)
        self.assertEqual(text.count(END), 1)
        self.assertEqual(text.rstrip('\n').splitlines()[-1], END)
        before = text[:text.index(BEGIN)]
        self.assertIn('create table if not exists public.comments (', before)
        self.assertNotIn('comment_replies', code_only(before), 'таблиця відповідей зʼявляється лише у позначеному блоці')

    def test_the_header_carries_the_three_warnings(self):
        header = split_header(_read('replies.sql'))[0]
        low = header.lower()
        for must in ('run this once', 'idempotent', 'only this file', 'never the whole `schema.sql`',
                     'unrelated table named `public.comment_replies`', 'create table if not exists', 'adopted'):
            self.assertIn(must, low, must)
        self.assertTrue(all(ln.startswith('--') for ln in header.splitlines() if ln.strip()), 'шапка — лише коментарі')

    def test_the_schema_header_mentions_the_replies_table(self):
        head = split_header(_read('schema.sql'))[0]
        self.assertIn('comment_replies', head)
        self.assertIn('replies.sql', head)

    def test_the_files_are_ascii_clean_of_names_and_hosts(self):
        for name in ('replies.sql',):
            text = _read(name)
            self.assertNotRegex(text, r'@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|https?://', name)


class CheckerSelfTest(unittest.TestCase):
    """Сам перевіряльник не мовчить: зіпсований текст він відхиляє (захист від тесту, що завжди зелений)."""

    def good(self):
        return split_header(_read('replies.sql'))[1]

    def rejects(self, sql):
        with self.assertRaises(AssertionError):
            check_sql(self, sql, 'mutant')

    def test_it_rejects_a_foreign_key_a_cascade_and_other_breakages(self):
        good = self.good()
        self.rejects(good.replace('  comment_id text not null,', '  comment_id text not null references public.comments(id) on delete cascade,'))
        self.rejects(good.replace('if n > 100', 'if n > 25'))
        self.rejects(good.replace('drop policy if exists clr_delete on public.comment_replies;', ''))
        self.rejects(good.replace('create index if not exists', 'create index'))
        self.rejects(good.replace('drop trigger if exists clr_delete_scope_guard on public.comment_replies;', ''))
        self.rejects(good.replace('set search_path = pg_catalog, public', '', 1))
        self.rejects(good.replace('revoke truncate, references, trigger', 'revoke truncate, trigger'))
        self.rejects(good.replace('add table public.comment_replies', 'add table public.comments'))

    def test_the_header_split_ignores_comments_inside_the_block(self):
        header, block = split_header('-- a\n\n-- b\ncreate table x;\n-- inner\n')
        self.assertEqual((header, block), ('-- a\n\n-- b', 'create table x;\n-- inner'))


if __name__ == '__main__':
    unittest.main()
