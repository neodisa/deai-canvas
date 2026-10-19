/* supabase-comments — браузерний адаптер ролі `comments` (спека 2b-2): сховище CommentLayer поверх supabase-js.
 *
 * Це порт `CommentLayerSupabase` і водночас еталон для авторів модулів: усе, що потрібно ядру, — одна фабрика,
 *   window.DeaiComments = { create(cfg) { return store; } };
 *   cfg   = { …client_config модуля (тут: url, key), channel, onChange }
 *   store = { ready, load(), save(comments), remove(ids), subscribe(fn), close() }
 * Файл вантажиться ПІСЛЯ `supabase.min.js` (глобальний `supabase`, supabase-js 2.110.0) — див. `client` у module.json.
 *
 * Таблиця `comments` (див. schema.sql). Усе звужене каналом задачі (`cfg.channel` → стовпець `project_id`):
 *   · читання — `select * … where project_id = канал order by id`;
 *   · запис — upsert за `id` (до 3 спроб), `project_id` завжди береться з каналу, а не з коментаря;
 *   · видалення — `id in (…) AND project_id = канал`: без другого фільтра один запит міг би зачепити чужий канал;
 *   · realtime — підписка `postgres_changes` на таблицю, а на кожну подію — перечитування каналу. Фільтра project_id у
 *     самій підписці нема навмисно: події DELETE несуть лише первинний ключ, і фільтр мовчки губив би видалення.
 * Ключ (публічний, anon / publishable) іде лише в `createClient`; адаптер його не друкує й нікуди не пише.
 * Інших глобальних імен, крім `window.DeaiComments`, не створює. */
(function () {
  var TABLE = 'comments';
  var ATTEMPTS = 3;                          // спроб запису; між ними 300, 600 мс (після останньої чекати нема чого)

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
    return {
      id: c.id, project_id: channel, author: c.author, text: c.text, status: c.status,
      fp: c.fp, html_snapshot: c.htmlSnapshot || null, meta: c.meta || null,
      born_v: c.bornV, resolved_v: c.resolvedV || null,
      resolve_reason: c.resolveReason || null, ts: c.ts || null
    };
  }

  function sleep(ms) { return new Promise(function (resolve) { setTimeout(resolve, ms); }); }

  function create(cfg) {
    var sb = window.supabase;
    if (!sb || typeof sb.createClient !== 'function') throw new Error('supabase-js is not loaded (expected the global `supabase`)');
    var client = sb.createClient(cfg.url, cfg.key);
    var channel = cfg.channel;
    var cache = [];
    var listeners = typeof cfg.onChange === 'function' ? [cfg.onChange] : [];
    var closed = false;
    var seq = 0;                             // номер останнього перечитування: стара відповідь не затирає свіжішу

    function emit() {
      for (var i = 0; i < listeners.length; i++) { try { listeners[i](cache); } catch (e) { /* підписник не валить решту */ } }
    }

    function fetchAll() {
      if (closed) return Promise.resolve();  // подія realtime після close() нічого не питає в бази
      var mine = ++seq;
      return Promise.resolve(client.from(TABLE).select('*').eq('project_id', channel).order('id')).then(function (res) {
        if (closed || mine !== seq) return;
        if (res.error) { console.warn('[deai-comments] supabase fetch failed:', res.error.message); return; }
        cache = (res.data || []).map(rowToComment);
        emit();
      });
    }

    var realtime = client.channel('cl-' + channel)
      .on('postgres_changes', { event: '*', schema: 'public', table: TABLE }, fetchAll)
      .subscribe();

    var ready = fetchAll();

    function upsert(rows, attempt) {
      return Promise.resolve(client.from(TABLE).upsert(rows, { onConflict: 'id' })).then(function (res) {
        if (!res.error) return null;
        if (attempt + 1 >= ATTEMPTS) return res.error;
        return sleep(300 * (attempt + 1)).then(function () { return upsert(rows, attempt + 1); });
      });
    }

    return {
      ready: ready,
      load: function () { return cache; },
      /* Живі оновлення: CommentLayer підписується тут; realtime → fetchAll → emit. */
      subscribe: function (fn) { if (typeof fn === 'function') listeners.push(fn); },
      save: function (comments) {
        var rows = comments.map(function (c) { return commentToRow(c, channel); });
        return upsert(rows, 0).then(function (err) {
          cache = comments.slice();          // оптимістичний кеш: запис не губиться, навіть якщо база не відповіла
          if (!err) return;
          console.warn('[deai-comments] supabase save failed after retries:', err.message);
          throw new Error('supabase save failed: ' + err.message);
        });
      },
      /* Жорстке видалення: upsert-збереження рядків не прибирає, тож видалення — окремий шлях. */
      remove: function (ids) {
        if (!ids || !ids.length) return Promise.resolve();
        return Promise.resolve(client.from(TABLE).delete().in('id', ids).eq('project_id', channel)).then(function (res) {
          if (res.error) console.warn('[deai-comments] supabase delete failed:', res.error.message);
          cache = cache.filter(function (c) { return ids.indexOf(c.id) < 0; });
        });
      },
      close: function () {
        if (closed) return;
        closed = true;
        listeners.length = 0;
        try { client.removeChannel(realtime); } catch (e) { /* канал уже знято */ }
      }
    };
  }

  window.DeaiComments = { create: create };
})();
