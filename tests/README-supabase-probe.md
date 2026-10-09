# Поведінкова перевірка прав у Supabase

Політики й тригери з `ops/supabase-policies.sql` перевіряються не читанням, а
поведінкою — від тієї самої ролі `anon`, якою ходять опубліковані сторінки.
Обидві перевірки нижче **не змінюють даних**: перша працює на фіктивних рядках
у транзакції з `rollback`, друга прибирає за собою.

Чому не автотест: обидві потребують живої бази й секретів, тому в `python3 -m
unittest` не входять. Доктор (`bin/doctor.py --all`) щоночі перевіряє те
підмножину, яку можна перевірити без запису — інваріант `anon-write-scope`.

## 1. Права й гварди (SQL Editor, від ролі anon)

Прогнати цілком у Supabase → SQL Editor. Мусить віддати 10 рядків, усі `pass = true`.

```sql
begin;
create temp table res(n text, pass boolean, note text);
grant all on res to anon;
set local role anon;

do $$ declare c int; begin
  select count(*) into c from public.comments;
  insert into res values ('read comments', c > 0, c || ' rows');
exception when others then insert into res values ('read comments', false, sqlerrm); end $$;

do $$ begin
  insert into public.comments(id, project_id, author, text, fp)
  values ('__probe_a__', '__probe_p1__', 'probe', 'x', '{}'::jsonb),
         ('__probe_b__', '__probe_p2__', 'probe', 'x', '{}'::jsonb);
  insert into res values ('insert comments', true, '2 rows');
exception when others then insert into res values ('insert comments', false, sqlerrm); end $$;

do $$ begin
  update public.comments set text = 'y' where id = '__probe_a__';
  insert into res values ('update text', true, 'ok');
exception when others then insert into res values ('update text', false, sqlerrm); end $$;

do $$ begin
  update public.comments set project_id = '__probe_p2__' where id = '__probe_a__';
  insert into res values ('BLOCK project_id move', false, 'дозволено!');
exception when others then insert into res values ('BLOCK project_id move', true, sqlerrm); end $$;

do $$ begin
  delete from public.comments where id in ('__probe_a__', '__probe_b__');
  insert into res values ('BLOCK cross-project delete', false, 'дозволено!');
exception when others then insert into res values ('BLOCK cross-project delete', true, sqlerrm); end $$;

do $$ begin
  delete from public.comments where id = '__probe_a__';
  insert into res values ('delete single pin', true, 'ok');
exception when others then insert into res values ('delete single pin', false, sqlerrm); end $$;

do $$ begin
  insert into public.comments(id, project_id, author, text, fp)
  select '__probe_bulk_' || g, '__probe_p3__', 'probe', 'x', '{}'::jsonb from generate_series(1, 26) g;
  delete from public.comments where project_id = '__probe_p3__';
  insert into res values ('BLOCK bulk delete >25', false, 'дозволено!');
exception when others then insert into res values ('BLOCK bulk delete >25', true, sqlerrm); end $$;

do $$ begin
  delete from public.overview_projects where id = '__probe_never_exists__';
  insert into res values ('BLOCK dashboard delete', false, 'дозволено!');
exception when others then insert into res values ('BLOCK dashboard delete', true, sqlerrm); end $$;

do $$ begin
  insert into public.overview_projects(id, name) values ('__probe_manual__', 'probe');
  update public.overview_projects set name = 'probe2' where id = '__probe_manual__';
  insert into res values ('dashboard insert+update 1', true, 'ok');
exception when others then insert into res values ('dashboard insert+update 1', false, sqlerrm); end $$;

do $$ begin
  insert into public.overview_projects(id, name)
  select '__probe_m_' || g, 'probe' from generate_series(1, 4) g;
  update public.overview_projects set name = 'z' where id like '\_\_probe\_m\_%';
  insert into res values ('BLOCK bulk dashboard update >3', false, 'дозволено!');
exception when others then insert into res values ('BLOCK bulk dashboard update >3', true, sqlerrm); end $$;

reset role;
select n, pass, left(note, 90) as note from res;
rollback;
```

⚠️ `rollback` в кінці обовʼязковий. Після прогону звір, що нічого не залишилось:

```sql
select count(*) from public.comments where project_id like '\_\_probe%';   -- 0
select count(*) from public.overview_projects where id like '\_\_probe%';  -- 0
```

## 2. Живий шлях через PostgREST (як його бачить сторінка)

SQL Editor ходить від ролі напряму, а сторінка — через PostgREST із
publishable-ключем. Це різні шляхи (наприклад `upsert` усього набору пінів — це
`INSERT … ON CONFLICT DO UPDATE`, і саме там спрацьовує row-тригер), тому шлях
сторінки перевіряється окремо:

```bash
python3 ops/rest_probe.py
```

Мусить віддати вісім `✅` і `РАЗОМ: усі перевірки пройдені`. Скрипт пише в
службовий `project_id`, якого немає в `tasks.json`, і прибирає за собою по
одному піну (масове видалення заблоковане гвардом — це теж частина перевірки).
