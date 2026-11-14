/* supabase-comments — браузерний адаптер ролі `comments` (спека 2b-2): сховище CommentLayer поверх supabase-js.
 *
 * Це порт `CommentLayerSupabase` і водночас еталон для авторів модулів: усе, що потрібно ядру, — одна фабрика,
 *   window.DeaiComments = { create(cfg) { return store; } };
 *   cfg   = { …client_config модуля (тут: url, key[, shotsBucket]), channel, onChange }
 *   store = { ready, load(), refresh(), save(comments), remove(ids), subscribe(fn), close()[, uploadShot(id, dataUrl)] }
 * Файл вантажиться ПІСЛЯ `supabase.min.js` (глобальний `supabase`, supabase-js 2.110.0) — див. `client` у module.json.
 *
 * Таблиця `comments` (див. schema.sql). Усе звужене каналом задачі (`cfg.channel` → стовпець `project_id`):
 *   · читання — `select * … where project_id = канал order by id`;
 *   · запис — upsert за `id` (до 3 спроб), `project_id` завжди береться з каналу, а не з коментаря;
 *   · видалення — `id in (…) AND project_id = канал`: без другого фільтра один запит міг би зачепити чужий канал;
 *   · realtime — підписка `postgres_changes` на таблицю, а на подію — перечитування каналу (з коротким згладжуванням: серія
 *     подій від одного upsert-а дає ОДНЕ перечитування). Фільтра project_id у самій підписці нема навмисно: події DELETE несуть
 *     лише первинний ключ, і фільтр мовчки губив би видалення; натомість колбек сам відсіює події чужих каналів
 *     (`relevant`: з 0.27.0 кожна сторінка задачі ЛІГИ підписана на командний канал, а без відсіву кожен коментар будь-де
 *     давав би `select *` зі знімками HTML у кожному відкритому вікні — урок квоти трафіку 21.10.2026);
 *   · запис різницею (0.27.0): `save` шле upsert лише рядків, що відрізняються від останнього прочитаного чи записаного знімка
 *     (порівняння — канонічним JSON із сортованими ключами: `jsonb` переставляє ключі `meta`); нема змін — нема запиту.
 * Клієнт supabase-js створюється БЕЗ автентифікації користувача (`persistSession`, `autoRefreshToken`, `detectSessionInUrl` —
 * вимкнені): за замовчуванням кожен `create()` запускав би інтервал оновлення токена, `BroadcastChannel`, записи в
 * сховище браузера й слухачі вікна, які `close()` не знімав би (а «Огляд» створює сховище на кожен запуск).
 * `close()` знімає канал і закриває сокет realtime, скасовує свої таймери: після нього адаптер нічого не тримає.
 * `uploadShot` зʼявляється лише коли в `cfg` є коректний `shotsBucket` (налаштування модуля `shots_bucket`): скріншот піна йде
 * в Storage цього ж проєкту. Ключ (публічний, anon / publishable) іде лише в `createClient` і заголовки `uploadShot`; адаптер
 * його не друкує й нікуди не пише.
 * Інших глобальних імен, крім `window.DeaiComments`, не створює. */
(function () {
  var TABLE = 'comments';
  var ATTEMPTS = 3;                          // спроб запису; між ними 300, 600 мс (після останньої чекати нема чого)
  var REFETCH_MS = 120;                      // згладжування подій realtime: одне перечитування на серію подій

  /* Рядок таблиці → коментар CommentLayer. `project_id` і `created_at` лишаються в базі. */
  function rowToComment(r) {
    return {
      id: r.id, author: r.author, text: r.text, status: r.status, fp: r.fp,
      htmlSnapshot: r.html_snapshot || null, meta: r.meta || null,
      bornV: r.born_v, resolvedV: r.resolved_v, resolveReason: r.resolve_reason, ts: r.ts
    };
  }

  /* Коментар CommentLayer → рядок таблиці. Канал ставить адаптер, а не вхідні дані. */
  function commentToRow(c, channel) {
    /* `undefined` → `null` (Б2, ревʼю задачі 3): база віддає null, і без цього свіжозбудований рядок відрізнявся б від прочитаного,
       а кожен save переписував би незмінені рядки. */
    function n(v) { return v === undefined ? null : v; }
    return {
      id: c.id, project_id: channel, author: n(c.author), text: n(c.text), status: n(c.status),
      fp: n(c.fp), html_snapshot: c.htmlSnapshot || null, meta: c.meta || null,
      born_v: n(c.bornV), resolved_v: c.resolvedV || null,
      resolve_reason: c.resolveReason || null, ts: c.ts || null
    };
  }

  function sleep(ms) { return new Promise(function (resolve) { setTimeout(resolve, ms); }); }
  function warn(what, e) { console.warn('[deai-comments] supabase ' + what + ':', e && e.message ? e.message : e); }

  /* Канонічний JSON (ключі обʼєктів відсортовано, `undefined` пропущено): Postgres `jsonb` переставляє ключі `meta`, і наївне
     `JSON.stringify` вважало б зміненим кожен рядок (поправка 8 плану Б2). */
  function stable(v) {
    if (Array.isArray(v)) return '[' + v.map(stable).join(',') + ']';
    if (v && typeof v === 'object') {
      return '{' + Object.keys(v).filter(function (k) { return v[k] !== undefined; }).sort()
        .map(function (k) { return JSON.stringify(k) + ':' + stable(v[k]); }).join(',') + '}';
    }
    return JSON.stringify(v === undefined ? null : v);
  }

  function create(cfg) {
    if (!cfg || typeof cfg.channel !== 'string' || !cfg.channel) throw new Error('DeaiComments.create: cfg.channel must be a non-empty string');
    var sb = window.supabase;
    if (!sb || typeof sb.createClient !== 'function') throw new Error('supabase-js is not loaded (expected the global `supabase`)');
    var client = sb.createClient(cfg.url, cfg.key, {
      auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false }
    });
    var channel = cfg.channel;
    var cache = [];
    var written = {};                        // id → stable(рядка), який база точно має (останнє читання чи успішний запис)
    var listeners = typeof cfg.onChange === 'function' ? [cfg.onChange] : [];
    var closed = false;
    var seq = 0;                             // «покоління» кешу: стара відповідь не затирає свіжішу, ні свій запис
    var refetchTimer = null;
    var SHOT_ID = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$/;      // той самий білий список, що `_AGENT_ID` ядра
    var bucket = typeof cfg.shotsBucket === 'string' && /^[a-z0-9][a-z0-9_-]{0,62}$/.test(cfg.shotsBucket) ? cfg.shotsBucket : '';
    var base = String(cfg.url).replace(/\/+$/, '');

    /* Скріншот піна → Storage (`<bucket>/comment-shots/<id>.jpg`, upsert); результат — публічна адреса або null. Форма
       адрес і заголовків — як у старого адаптера ЛІГИ: її бере картка Teams із `meta.shotUrl`. Ніколи не кидає. */
    function uploadShot(id, dataUrl) {
      if (closed || typeof id !== 'string' || !SHOT_ID.test(id) || typeof dataUrl !== 'string' || !/^data:image\//.test(dataUrl)) {
        return Promise.resolve(null);
      }
      var path = 'comment-shots/' + id + '.jpg';
      var type = (dataUrl.match(/^data:([^;,]+)/) || [0, 'image/jpeg'])[1];
      return Promise.resolve().then(function () { return fetch(dataUrl); })
        .then(function (r) { return r.blob(); })
        .then(function (blob) {
          return fetch(base + '/storage/v1/object/' + bucket + '/' + path, {
            method: 'POST',
            headers: { apikey: cfg.key, Authorization: 'Bearer ' + cfg.key, 'Content-Type': type, 'x-upsert': 'true', 'Cache-Control': '3600' },
            body: blob
          });
        })
        .then(function (res) {
          if (res && res.ok) return base + '/storage/v1/object/public/' + bucket + '/' + path;
          warn('shot upload failed', 'HTTP ' + (res && res.status));
          return null;
        })
        .catch(function (e) { warn('shot upload failed', e); return null; });
    }

    function emit() {
      for (var i = 0; i < listeners.length; i++) { try { listeners[i](cache); } catch (e) { /* підписник не валить решту */ } }
    }

    /* Помилка ЧИТАННЯ (квота 402, мережа): `ready` усе одно здається (інші споживачі на нього покладаються), тож без цього
       поля подвійне сховище не знало б, що команда лежить, і порожній кеш виглядав би «командних нема». Скидається
       першим вдалим читанням. */
    var loadError = null;
    function fetchAll() {
      if (closed) return Promise.resolve();  // подія realtime після close() нічого не питає в бази
      var mine = ++seq;
      return Promise.resolve(client.from(TABLE).select('*').eq('project_id', channel).order('id')).then(function (res) {
        if (closed || mine !== seq) return;
        if (res.error) { loadError = String(res.error.message || res.error); warn('fetch failed', res.error); return; }
        loadError = null;
        cache = (res.data || []).map(rowToComment);
        written = {};
        cache.forEach(function (c) { written[c.id] = stable(commentToRow(c, channel)); });
        emit();
      }).catch(function (e) { loadError = String((e && e.message) || e); warn('fetch failed', e); });
    }

    /* Подія realtime → перечитування через `REFETCH_MS`; нова подія в цей час посуває термін, а не додає запит. */
    function scheduleFetch() {
      if (closed) return;
      if (refetchTimer !== null) clearTimeout(refetchTimer);
      refetchTimer = setTimeout(function () { refetchTimer = null; fetchAll(); }, REFETCH_MS);
    }

    /* Подія realtime стосується НАШОГО каналу? Підписка — на всю таблицю (DELETE несе лише ключ, фільтр у підписці губив би
       видалення), тож відсіюємо тут: без цього кожен коментар будь-де давав би `select *` у кожному відкритому вікні
       (з Б2 кожна сторінка задачі підписана; урок квоти трафіку 21.10.2026). */
    function relevant(p) {
      var n = p && p.new, o = p && p.old;
      if (n && n.project_id != null) return n.project_id === channel;
      var id = o && o.id;
      if (id == null) return true;                       // незнайома форма — краще перечитати
      return cache.some(function (c) { return c.id === id; });
    }

    var realtime = client.channel('cl-' + channel)
      .on('postgres_changes', { event: '*', schema: 'public', table: TABLE }, function (p) { if (relevant(p)) scheduleFetch(); })
      .subscribe();

    var ready = fetchAll();

    function upsert(rows, attempt) {
      return Promise.resolve(client.from(TABLE).upsert(rows, { onConflict: 'id' })).then(function (res) {
        if (!res.error) return null;
        if (attempt + 1 >= ATTEMPTS) return res.error;
        return sleep(300 * (attempt + 1)).then(function () { return upsert(rows, attempt + 1); });
      });
    }

    var store = {
      ready: ready,
      get loadError() { return loadError; },
      load: function () { return cache; },
      /* Примусове перечитування (його кличе «Огляд» при поверненні на нього). */
      refresh: function () { return fetchAll(); },
      /* Живі оновлення: CommentLayer підписується тут; realtime → fetchAll → emit. */
      subscribe: function (fn) { if (typeof fn === 'function') listeners.push(fn); },
      save: function (comments) {
        var rows = comments.map(function (c) { return commentToRow(c, channel); });
        /* Запис РІЗНИЦЕЮ (Deai 0.27.0): лише рядки, яких база ще не має в такому вигляді. Застарілий список одного вікна вже не
           перетирає чужого закриття чи доручення в РЕШТІ рядків; два записи в ОДИН рядок — виграє останній. */
        var changed = rows.filter(function (r) { return written[r.id] !== stable(r); });
        if (!changed.length) { cache = comments.slice(); seq++; return Promise.resolve(); }
        return upsert(changed, 0).then(function (err) {
          cache = comments.slice();          // оптимістичний кеш: запис не губиться, навіть якщо база не відповіла
          seq++;                             // а відповідь, що вже летіла до запису, його не затре
          if (!err) { changed.forEach(function (r) { written[r.id] = stable(r); }); return; }
          warn('save failed after retries', err);
          throw new Error('supabase save failed: ' + err.message);
        });
      },
      /* Жорстке видалення: upsert-збереження рядків не прибирає, тож видалення — окремий шлях. */
      remove: function (ids) {
        if (!ids || !ids.length) return Promise.resolve();
        return Promise.resolve(client.from(TABLE).delete().in('id', ids).eq('project_id', channel)).then(function (res) {
          if (res.error) warn('delete failed', res.error);
          cache = cache.filter(function (c) { return ids.indexOf(c.id) < 0; });
          ids.forEach(function (id) { delete written[id]; });
          seq++;
        });
      },
      close: function () {
        if (closed) return;
        closed = true;
        listeners.length = 0;
        if (refetchTimer !== null) { clearTimeout(refetchTimer); refetchTimer = null; }
        /* removeChannel лише залишає канал; сокет realtime (з серцебиттям) закриває `disconnect`. Обидва — без відмов назовні. */
        var left;
        try { left = Promise.resolve(client.removeChannel(realtime)); } catch (e) { left = Promise.resolve(); }
        left.catch(function () { /* вже знято */ })
          .then(function () { return client.realtime.disconnect(); })
          .catch(function () { /* вже закрито */ });
      }
    };
    if (bucket) store.uploadShot = uploadShot;
    return store;
  }

  window.DeaiComments = { create: create };
})();
