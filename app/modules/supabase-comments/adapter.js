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
 *   · знімок каналу між перезавантаженнями рамки (0.27.0): робоче місце ЛІГИ перезавантажує рамку на кожен клік сторінки/стану/
 *     ітерації, і кожне перезавантаження створювало новий адаптер із повним `select *` (до ~700 КБ на канал: 75% — вбудований
 *     `meta.shot`; стовпці обрізати не можна — `save` пише рядки цілком). Тому останнє ВДАЛЕ повне читання лежить у
 *     `sessionStorage` вкладки (ключ `deai-comments:v1:<хост url>:<канал>`, значення `{t, rows}`) і живе `CACHE_TTL_MS` (2 хв):
 *     свіжий знімок засіває кеш без читання з бази, realtime підписується як завжди. Власні `save`/`remove` оновлюють рядки
 *     знімка, але НЕ `t` (інакше власні записи вічно продовжували б його життя, і повного читання не було б ніколи); луна
 *     власного запису в realtime (рядок збігається з `written`) нового читання не планує; `refresh()` у межах TTL мережі не
 *     торкається. Застарілість обмежена 2 хв: засіяний адаптер робить ОДНЕ фонове «наздоганяюче» читання через `TTL - вік`
 *     (скасовується лише ВДАЛИМ повним читанням чи `close()`; невдале чи витіснене наздоганяюче читання повторюється раз на TTL,
 *     доки одне не вдасться; далі realtime підписаний без прогалини) — тож і зміна, що випала в проміжок між рамками,
 *     зʼявляється щонайбільше за 2 хв. Порожнє читання-«пустушка» помітить id як видалений (`gone`) до наступного повного читання (≤ ~2 хв). Засіяний адаптер НЕ показує смугу «команда впала» для збою, що почався
 *     після знімка (`loadError` читає лише `checkLoad` дуал-сховища, раз після `ready`); записи й далі ретраяться через дуал-сховище. Запис ДО першого власного повного
 *     читання (`seeded && !freshRead`) не сліпий: `save` спершу питає в бази лише змінені id (`in('id', …)`) і зливає
 *     поле-за-полем (і ключ-за-ключем `meta`) трійкою база(`written`)/наше/їхнє; обидва змінили — наше (як до кешу).
 *     Знімок спільний для рамок вкладки: `syncSnap` пише, лише якщо `t` у сховищі — наш (інакше затер би новіше читання).
 *     Без `sessionStorage` (чи коли він кидає) адаптер поводиться як раніше. Сховище, що переживає вкладку, не використовується навмисно.
 * Відповіді на коментарі (0.34) — окрема таблиця `comment_replies` (replies.sql), без FK. `fetchAll` читає обидві таблиці паралельно
 * (відповіді `order created_at, id`); збій відповідей коментарів не псує: `supportsReplies=false`, `repliesDown` = 'no-replies-schema'
 * (таблиці нема: PGRST205/42P01/404) чи текст помилки. Відповіді — у `comment.replies` лише в памʼяті адаптера (рядок коментаря
 * не змінюється); пишуться РІЗНИЦЕЮ (`writtenReplies`/`replyOwner`) після коментарів: upsert, потім delete за id (≤100 на запит).
 * `remove` спершу видаляє відповіді за comment_id (по 10 коментарів; при відмові — відомі id пачками ≤100), збій коментар не блокує.
 * Realtime відповідей — ОКРЕМИМ каналом `clr-<канал>`, що відкривається лише коли таблиця є (привʼязка до неіснуючої таблиці могла б
 * завалити приєднання каналу коментарів). Знімок сесії: `{t, rows, replies, rd}`; знімок без масиву `replies` не засіває.
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
  var REPLIES = 'comment_replies';           // відповіді на коментарі — окрема таблиця (replies.sql), без FK
  var ATTEMPTS = 3;                          // спроб запису; між ними 300, 600 мс (після останньої чекати нема чого)
  var REFETCH_MS = 120;                      // згладжування подій realtime: одне перечитування на серію подій
  var CACHE_TTL_MS = 120000;                 // вік знімка каналу в sessionStorage, до якого повного читання не потрібно
  var NET_TIMEOUT_MS = 20000;                // скільки чекаємо відповіді бази на запис чи звірку: напівмертве зʼєднання не вішає чергу
  var CACHE_PREFIX = 'deai-comments:v1:';
  var CACHE_MAX_CHARS = 2000000;             // більший знімок не зберігаємо (ліміт sessionStorage ~5 МБ на всі ключі origin-а)

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

  /* Відповідь коментатора {id, author, text, ts, editedTs?, agent?} ↔ рядок `comment_replies`. Окремо від коментаря: рядок
     коментаря (11 полів) не змінюється, відповіді липнуть до нього лише в памʼяті адаптера. Збирається з відомих полів — ядро
     дописує до обʼєктів службові (`_pending` тощо). */
  function replyToRow(r, commentId, channel) {
    function n(v) { return v === undefined ? null : v; }
    return {
      id: r.id, comment_id: commentId, project_id: channel, author: n(r.author), text: n(r.text),
      ts: r.ts || null, edited_ts: r.editedTs || null, agent: r.agent === true
    };
  }
  function rowToReply(r) {
    var o = { id: r.id, author: r.author, text: r.text, ts: r.ts };
    if (r.edited_ts != null) o.editedTs = r.edited_ts;
    if (r.agent === true) o.agent = true;
    return o;
  }
  /* Таблиці нема (PostgREST PGRST205 «не в кеші схеми», Postgres 42P01, чи просто HTTP 404): `replies.sql` ще не виконано. */
  function noTable(res) {
    var e = res && res.error;
    return !!e && (e.code === 'PGRST205' || e.code === '42P01' || e.status === 404 || res.status === 404);
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

  /* sessionStorage вкладки або null: сам доступ до `window.sessionStorage` може кидати (заблоковані дані сайту). */
  function snapStorage() {
    try { return window.sessionStorage || null; } catch (e) { return null; }
  }

  /* Знімок за ключем → {t, rows} або null; зіпсований запис видаляється. Кожен доступ — у try/catch. */
  function readSnap(ss, key) {
    try {
      var raw = ss.getItem(key);
      if (raw == null) return null;
      var o = JSON.parse(raw);
      var ok = o && typeof o.t === 'number' && isFinite(o.t) && Array.isArray(o.rows) &&
        o.rows.every(function (r) { return r && typeof r === 'object' && r.id != null; });
      if (ok) return o;
      ss.removeItem(key);
    } catch (e) { try { ss.removeItem(key); } catch (e2) { /* нема що робити */ } }
    return null;
  }

  function snapKeys(ss) {
    var keys = [];
    for (var i = 0; i < ss.length; i++) { var k = ss.key(i); if (k && k.indexOf(CACHE_PREFIX) === 0) keys.push(k); }
    return keys;
  }

  /* Записати знімок {t, rows, replies, rd} (рядки відповідей і причина, чому їх нема: null чи рядок). Завеликий — не зберігаємо й прибираємо старий; квота — чистимо всі наші ключі й одна повторна
     спроба; решту мовчки здаємо. Заодно вичищаємо чужі знімки старші за TTL. */
  function writeSnap(ss, key, t, rows, replies, rd) {
    try {
      var val = JSON.stringify({ t: t, rows: rows, replies: replies, rd: rd });
      if (val.length > CACHE_MAX_CHARS) { ss.removeItem(key); return; }
      var now = Date.now();
      snapKeys(ss).forEach(function (k) {
        if (k === key) return;
        var o = readSnap(ss, k);
        if (!o || now - o.t >= CACHE_TTL_MS || o.t > now) ss.removeItem(k);
      });
      try { ss.setItem(key, val); } catch (e) {
        snapKeys(ss).forEach(function (k) { ss.removeItem(k); });
        ss.setItem(key, val);
      }
    } catch (e) { /* знімок — лише оптимізація */ }
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
    var writtenReplies = {};                 // id відповіді → stable(її рядка), який база має; replyOwner: id відповіді → id коментаря
    var replyOwner = {};
    var supportsReplies = false;             // таблиця comment_replies є й читається (після першого вдалого читання/знімка)
    var repliesDown = null;                  // null чи причина: 'no-replies-schema' (таблиці нема) або текст помилки
    var goneReplies = {};                    // надгробки: id відповідей, видалених кимось іще (чи нами): ні upsert, ні delete
    var lastCarried = {};                    // id відповідей, що ніс ОСТАННІЙ виклик save (до їх запису в базу)
    var retryDel = {};                       // id відповідей, чиє видалення впало: наступні save повторюють його, а не «забувають»
    var noSchemaWarned = false;
    var lastFetch = 0;                       // `mine` останнього запущеного fetchAll: відрізняє «витіснене save» від «витіснене новішим читанням»
    var badWarned = {};                      // id некоректних відповідей, про які вже попереджено
    var repliesRealtime = null;              // окремий канал realtime для відповідей (лише коли таблиця є)
    var listeners = typeof cfg.onChange === 'function' ? [cfg.onChange] : [];
    var closed = false;
    var seq = 0;                             // «покоління» кешу: стара відповідь не затирає свіжішу, ні свій запис
    var refetchTimer = null;
    var SHOT_ID = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$/;      // той самий білий список, що `_AGENT_ID` ядра
    var bucket = typeof cfg.shotsBucket === 'string' && /^[a-z0-9][a-z0-9_-]{0,62}$/.test(cfg.shotsBucket) ? cfg.shotsBucket : '';
    var base = String(cfg.url).replace(/\/+$/, '');

    /* Знімок каналу (див. шапку). `snapT` — мітка останнього вдалого повного читання (власного чи засіяного); null — читання
       ще не було. Без sessionStorage `ss` = null, і нічого з цього не діє. */
    var ss = snapStorage();
    var snapKey = CACHE_PREFIX + String(cfg.url).replace(/^[a-z][a-z0-9+.-]*:\/\//i, '').split(/[\/?#]/)[0].toLowerCase() + ':' + channel;
    var snapT = null;
    var seeded = false;                      // кеш засіяно знімком (а не власним читанням)
    var freshRead = false;                   // цей екземпляр уже завершив власне вдале повне читання
    var gone = {};                           // id, які колега видалив (знайдено цільовим select-ом): ніколи не пишемо їх назад
    var checked = {};                        // id, уже звірені цільовим select-ом: після нашого злитого запису авторитетні
    var chain = Promise.resolve();           // черга власних save: запис N+1 починається після завершення N
    var catchTimer = null;                   // одноразове наздоганяюче читання засіяного екземпляра
    function fresh() {
      if (snapT === null) return false;
      var age = Date.now() - snapT;
      return age >= 0 && age < CACHE_TTL_MS;
    }
    /* Власний запис чи видалення: рядки знімка = новий кеш, `t` — той, що вже лежить у сховищі (життя знімка не продовжуємо). */
    function syncSnap() {
      if (!ss || snapT === null) return;
      var o = readSnap(ss, snapKey);
      if (!o || o.t !== snapT) return;       // знімок оновив чужий екземпляр (новіше читання): не затираємо його своїми старішими рядками
      writeSnap(ss, snapKey, o.t, cache.map(function (c) { return commentToRow(c, channel); }), confirmedReplyRows(), repliesDown);
    }
    /* Рядки відповідей, які база ТОЧНО має (writtenReplies, у порядку вставки): знімок не повинен вважати збереженим те, що
       впало при записі, — після перезавантаження воно б уже ніколи не пішло в базу. */
    function confirmedReplyRows() {
      var out = [];
      Object.keys(writtenReplies).forEach(function (id) { try { out.push(JSON.parse(writtenReplies[id])); } catch (e) { /* пропускаємо */ } });
      return out;
    }
    function keysOf(o) { var m = {}; Object.keys(o).forEach(function (k) { m[k] = true; }); return m; }
    function carriedIds(list) {
      var m = {};
      (list || []).forEach(function (c) {
        (c && Array.isArray(c.replies) ? c.replies : []).forEach(function (r) { if (r && typeof r.id === 'string') m[r.id] = true; });
      });
      return m;
    }
    /* Відповіді, що прийшли ззовні (читання чи подія) ПОКИ save був у черзі чи в польоті, а викликач їх ніколи не бачив
       (не в `fl.base`), лишаються в кеші: `cache = comments.slice()` інакше їх губив би. true — щось повернули. */
    function reattachForeign(fl, carried) {
      var any = false;
      var byOwner = {};
      Object.keys(writtenReplies).forEach(function (id) {
        if (carried[id] || fl.base[id] || goneReplies[id] || retryDel[id]) return;
        (byOwner[replyOwner[id]] = byOwner[replyOwner[id]] || []).push(id);
      });
      cache = cache.map(function (c) {
        var ids = byOwner[c.id];
        if (!ids) return c;
        var have = {};
        (Array.isArray(c.replies) ? c.replies : []).forEach(function (r) { if (r) have[r.id] = true; });
        var add = [];
        ids.forEach(function (id) { if (!have[id]) { try { add.push(rowToReply(JSON.parse(writtenReplies[id]))); } catch (e) { /* пропускаємо */ } } });
        if (!add.length) return c;
        any = true;
        var copy = Object.assign({}, c);
        copy.replies = (Array.isArray(c.replies) ? c.replies : []).concat(add);
        return copy;
      });
      return any;
    }
    /* Рядки відповідей → до коментарів кешу за comment_id (у порядку, як віддала база; сироти відкидаємо); перебудувати
       знімки writtenReplies/replyOwner. `replies` ставимо лише коментарю, що їх має. */
    function attachReplies(list, repRows) {
      var byId = {};
      list.forEach(function (c) { byId[c.id] = c; });
      writtenReplies = {}; replyOwner = {};
      (repRows || []).forEach(function (r) {
        var c = r && typeof r.id === 'string' ? byId[r.comment_id] : null;
        if (!c) return;
        (c.replies = c.replies || []).push(rowToReply(r));
        writtenReplies[r.id] = stable(replyToRow(rowToReply(r), r.comment_id, channel));
        replyOwner[r.id] = r.comment_id;
      });
    }
    /* Realtime відповідей — ОКРЕМИМ каналом (рішення контролера): привʼязка postgres_changes до таблиці, якої нема чи яку не
       опубліковано, могла б завалити приєднання всього каналу, і коментарі в проєктах без replies.sql втратили б «живе». Відкриваємо
       один раз, коли таблиця вперше виявилась придатною. */
    function openRepliesChannel() {
      if (closed || repliesRealtime !== null || !supportsReplies) return;
      repliesRealtime = client.channel('clr-' + channel)
        .on('postgres_changes', { event: '*', schema: 'public', table: REPLIES }, function (p) {
          /* DELETE несе лише ключ (`old: {id}`): відома нам відповідь, видалена кимось, більше не пишеться (не воскресає зі
             застарілого save) — ще ДО перечитування. */
          var od = p && p.eventType === 'DELETE' && p.old && p.old.id;
          if (od != null && writtenReplies[od] !== undefined) goneReplies[od] = true;
          if (relevantReply(p) && !ownEchoReply(p)) scheduleFetch();
        })
        .subscribe();
    }
    function relevantReply(p) {
      var n = p && p.new, o = p && p.old;
      if (n && n.project_id != null) return n.project_id === channel;
      var id = o && o.id;
      if (id == null) return true;
      return writtenReplies[id] !== undefined;
    }
    function ownEchoReply(p) {
      try {
        var n = p && p.new;
        if (!n || n.id == null || (p.eventType !== 'INSERT' && p.eventType !== 'UPDATE')) return false;
        return writtenReplies[n.id] === stable(replyToRow(rowToReply(n), n.comment_id, channel));
      } catch (e) { return false; }
    }

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
    /* Наздоганяюче читання, що не вдалось чи було витіснене, не вмирає: ще одна спроба через TTL (не частіше одного разу на 2 хв). */
    function scheduleCatch(ms) {
      if (closed || freshRead || catchTimer !== null) return;
      catchTimer = setTimeout(function () { catchTimer = null; fetchAll(true); }, ms);
    }
    function fetchAll(fromCatch) {
      if (closed) return Promise.resolve();  // подія realtime після close() нічого не питає в бази
      var mine = ++seq;
      lastFetch = mine;
      var lost = function () { if (fromCatch === true) scheduleCatch(CACHE_TTL_MS); };
      /* Обидві таблиці — паралельно; відповіді не можуть зламати читання коментарів (їхня помилка стає `repliesDown`). */
      var cq = Promise.resolve(client.from(TABLE).select('*').eq('project_id', channel).order('id'));
      var rq;
      try { rq = Promise.resolve(client.from(REPLIES).select('*').eq('project_id', channel).order('created_at').order('id')).catch(function (e) { return { error: e }; }); }
      catch (e) { rq = Promise.resolve({ error: e }); }
      return Promise.all([cq, rq]).then(function (both) {
        var res = both[0], rres = both[1] || {};
        if (closed || mine !== seq) {
          lost();
          /* Витіснене НАШИМ save/remove (а не новішим читанням) — зміна ззовні, що його запустила, не губиться: ще одне читання. */
          if (!closed && lastFetch === mine) scheduleFetch();
          return;
        }
        if (res.error) { loadError = String(res.error.message || res.error); warn('fetch failed', res.error); lost(); return; }
        loadError = null;
        freshRead = true;
        if (catchTimer !== null) { clearTimeout(catchTimer); catchTimer = null; }   // повне читання вдалось: наздоганяти нічого
        (res.data || []).forEach(function (r) { delete gone[r.id]; });
        cache = (res.data || []).map(rowToComment);
        written = {};
        cache.forEach(function (c) { written[c.id] = stable(commentToRow(c, channel)); });
        var repRows = [];
        if (!rres.error) {
          supportsReplies = true; repliesDown = null;
          repRows = rres.data || [];
          /* Надгробки: відома нам відповідь, якої застосоване читання вже не віддало, видалена кимось іще (читання, що застосовується,
             відображає кожен наш завершений запис: save після запису збільшує seq). Повернулась у читанні — надгробок знімаємо. */
          var seenIds = {};
          repRows.forEach(function (r) { if (r && r.id != null) seenIds[r.id] = true; });
          Object.keys(writtenReplies).forEach(function (id) { if (!seenIds[id]) goneReplies[id] = true; });
          Object.keys(seenIds).forEach(function (id) { delete goneReplies[id]; });
          Object.keys(retryDel).forEach(function (id) { if (!seenIds[id]) delete retryDel[id]; });   // база вже без неї: повторювати нічого
          attachReplies(cache, repRows);
        } else if (noTable(rres)) {
          supportsReplies = false; repliesDown = 'no-replies-schema';
          writtenReplies = {}; replyOwner = {};
        } else {
          /* Тимчасова помилка: відомі відповіді лишаються (і в кеші, щоб не зникали з екрана), запис відповідей призупинено. */
          supportsReplies = false;
          repliesDown = String(rres.error.message || rres.error);
          warn('replies fetch failed', rres.error);
          var byId = {};
          cache.forEach(function (c) { byId[c.id] = c; });
          Object.keys(writtenReplies).forEach(function (id) {
            var c = byId[replyOwner[id]];
            if (!c || goneReplies[id]) return;
            try { (c.replies = c.replies || []).push(rowToReply(JSON.parse(writtenReplies[id]))); } catch (e) { /* пропускаємо */ }
          });
        }
        if (ss) { snapT = Date.now(); writeSnap(ss, snapKey, snapT, res.data || [], confirmedReplyRows(), repliesDown); }
        openRepliesChannel();
        emit();
      }).catch(function (e) { loadError = String((e && e.message) || e); warn('fetch failed', e); lost(); });
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
      .on('postgres_changes', { event: '*', schema: 'public', table: TABLE }, function (p) { if (relevant(p) && !ownEcho(p)) scheduleFetch(); })
      .subscribe();

    /* Луна власного запису: INSERT/UPDATE, чий новий рядок (після того ж перетворення, що й при читанні) збігається з тим, що
       адаптер уже має в `written`, — нового читання не варте (кожен власний save інакше давав би повний `select *`). Усе інше,
       зокрема відсутній `new` чи обрізані стовпці, не збігається й перечитується, як раніше. DELETE іде через `relevant`. */
    function ownEcho(p) {
      try {
        var n = p && p.new;
        if (!n || n.id == null || (p.eventType !== 'INSERT' && p.eventType !== 'UPDATE')) return false;
        return written[n.id] === stable(commentToRow(rowToComment(n), channel));
      } catch (e) { return false; }
    }

    /* Свіжий знімок засіває кеш без читання з бази: `ready` здається, `onChange` усе одно повідомляється (як після читання). */
    if (ss) {
      var snap = readSnap(ss, snapKey);
      var age = snap ? Date.now() - snap.t : -1;
      /* Знімок БЕЗ масиву `replies` (старого формату) не засіває: відповідей у ньому нема, і адаптер вважав би, що їх немає в базі. */
      var snapOk = snap && Array.isArray(snap.replies) && (snap.rd == null || typeof snap.rd === 'string') &&
        snap.replies.every(function (r) { return r && typeof r === 'object' && r.id != null; });
      if (snapOk && age >= 0 && age < CACHE_TTL_MS) {
        cache = snap.rows.map(rowToComment);
        cache.forEach(function (c) { written[c.id] = stable(commentToRow(c, channel)); });
        repliesDown = snap.rd == null ? null : snap.rd;
        supportsReplies = snap.rd == null;
        attachReplies(cache, snap.replies);
        openRepliesChannel();
        snapT = snap.t;
        seeded = true;
        /* Наздоганяюче читання: без нього засіяний екземпляр не побачив би зміни, що сталась, коли в вкладці ніхто не слухав
           realtime (проміжок між рамками, чи користувач був на іншій задачі). Одне, на кінець життя знімка. */
        catchTimer = setTimeout(function () { catchTimer = null; fetchAll(true); }, CACHE_TTL_MS - age);
      }
    }
    var ready = seeded ? Promise.resolve().then(function () { if (!closed) emit(); }) : fetchAll();

    /* Відповідь бази АБО помилка `timeout` через NET_TIMEOUT_MS (напівмертве зʼєднання інакше вішало б усю чергу save). Таймер
       знімається при завершенні й при close(); пізня відповідь після таймауту ігнорується. */
    function raced(make) {
      return new Promise(function (resolve, reject) {
        var t = null, done = false;
        function fin(fn, v) { if (done) return; done = true; if (t !== null) { clearTimeout(t); t = null; } netPending.splice(netPending.indexOf(abort), 1); fn(v); }
        function abort(msg) { fin(resolve, { error: { message: msg } }); }
        netPending.push(abort);
        t = setTimeout(function () { t = null; abort('timeout'); }, NET_TIMEOUT_MS);
        Promise.resolve().then(make).then(function (v) { fin(resolve, v); }, function (e) { fin(reject, e); });
      });
    }
    var netPending = [];                     // незавершені запити з таймером: close() здає їх помилкою, а не лишає висіти

    function upsert(rows, attempt, table) {
      return raced(function () { return client.from(table).upsert(rows, { onConflict: 'id' }); }).then(function (res) {
        if (!res.error) return null;
        if (attempt + 1 >= ATTEMPTS) return res.error;
        return sleep(300 * (attempt + 1)).then(function () { return upsert(rows, attempt + 1, table); });
      });
    }

    /* Трійкове злиття одного рядка (див. шапку): база/наше/їхнє по стовпцю, а `meta` — по ключах верхнього рівня. */
    function same(a, b) { return stable(a) === stable(b); }
    function pick(b, o, t) { return same(o, b) ? t : (same(t, b) ? o : o); }
    function mergeRow(base, ours, theirs) {
      var out = {};
      /* Стан закриття (`status`, `resolved_v`, `resolve_reason`) — ОДНА одиниця: змішана трійка (статус колеги з причиною нашою)
         була б неузгодженою. Правило те саме: наша трійка = база → їхня; їхня = база → наша; обидві змінено → наша. */
      var tri = function (r) { return { status: r.status, resolved_v: r.resolved_v, resolve_reason: r.resolve_reason }; };
      var win = pick(tri(base), tri(ours), tri(theirs));
      out.status = win.status; out.resolved_v = win.resolved_v; out.resolve_reason = win.resolve_reason;
      Object.keys(ours).concat(Object.keys(theirs), Object.keys(base)).forEach(function (k) {
        if (k === 'id' || k === 'project_id' || k in out) return;
        if (k === 'meta' && ours.meta && theirs.meta && base.meta) {
          var m = {};
          Object.keys(ours.meta).concat(Object.keys(theirs.meta), Object.keys(base.meta)).forEach(function (mk) {
            if (mk in m) return;
            var o = ours.meta[mk], t = theirs.meta[mk], b = base.meta[mk], v;
            if (o === undefined && b !== undefined && !same(t, b)) v = t;    // наше видалення ключа чинне, лише якщо їхнє лишилось базовим
            else v = pick(b, o, t);
            m[mk] = v;
          });
          Object.keys(m).forEach(function (mk) { if (m[mk] === undefined) delete m[mk]; });
          out.meta = m;
        } else out[k] = pick(base[k], ours[k], theirs[k]);
      });
      out.id = ours.id; out.project_id = channel;
      return out;
    }
    /* Запис ДО першого власного повного читання: `written` може бути зі старого знімка, тож змінені рядки звіряємо з базою
       (лише їхні id, і лише ті, що ще не звірені) і зливаємо. Рядок, якого в базі вже нема (колега видалив) при ВДАЛОМУ запиті,
       вважаємо видаленим: не воскрешаємо (див. `gone`). Збій запиту — звичайний запис (користувача не блокуємо).
       Повертає {rows: рядки до upsert-а, gone: id видалених колегою}. */
    function precheck(changed) {
      var ids = changed.filter(function (r) { return !checked[r.id] && written[r.id] !== undefined; }).map(function (r) { return r.id; });
      if (!ids.length) return Promise.resolve({ rows: changed, gone: [] });
      return raced(function () { return client.from(TABLE).select('*').in('id', ids).eq('project_id', channel); }).then(function (res) {
        if (res.error) { warn('merge check failed', res.error); return { rows: changed, gone: [] }; }
        var remote = {}, goneIds = [];
        (res.data || []).forEach(function (r) { remote[r.id] = r; });
        ids.forEach(function (id) { checked[id] = true; });
        var rows = [];
        changed.forEach(function (r) {
          if (ids.indexOf(r.id) < 0 || written[r.id] === undefined) { rows.push(r); return; }
          if (!remote[r.id]) { goneIds.push(r.id); return; }
          var theirs = commentToRow(rowToComment(remote[r.id]), channel);
          rows.push(stable(theirs) === written[r.id] ? r : mergeRow(JSON.parse(written[r.id]), r, theirs));
        });
        return { rows: rows, gone: goneIds };
      }).catch(function (e) { warn('merge check failed', e); return { rows: changed, gone: [] }; });
    }

    /* Що з відповідей треба записати: рядки до upsert-а (відрізняються від `writtenReplies`) і id до видалення (були в базі,
       а коментар, що ними володів і лишається в списку, їх більше не несе). Без таблиці відповідей — нічого. */
    function planReplies(comments, fl) {
      var up = [], del = [], block = false;
      if (!supportsReplies) {
        /* Відповіді недоступні. Тимчасовий збій (repliesDown — повідомлення): save з незбереженою відповіддю мусить ВІДХИЛИТИСЬ,
           інакше коментатор зніме _pending, і відповідь зникне мовчки. Таблиці нема назавжди ('no-replies-schema'): відкидаємо з
           одним попередженням (інтерфейс не пропонує відповідей у такому проєкті). */
        var lost = false;
        comments.forEach(function (c) {
          (Array.isArray(c.replies) ? c.replies : []).forEach(function (r) {
            if (!r || typeof r.id !== 'string' || goneReplies[r.id]) return;
            if (typeof r.author !== 'string' || typeof r.text !== 'string') return;
            if (writtenReplies[r.id] !== stable(replyToRow(r, c.id, channel))) lost = true;
          });
        });
        if (lost && typeof repliesDown === 'string') {
          if (repliesDown === 'no-replies-schema') { if (!noSchemaWarned) { noSchemaWarned = true; warn('replies dropped', 'table comment_replies is missing in this project'); } }
          else block = true;
        }
        return { up: up, del: del, block: block };
      }
      var kept = {}, have = {}, seen = {};
      comments.forEach(function (c) {
        kept[c.id] = true;
        (Array.isArray(c.replies) ? c.replies : []).forEach(function (r) {
          if (!r || typeof r.id !== 'string') return;       // без рядкового id у цьому сховищі відповіді не живуть
          have[r.id] = true;                                // несена відповідь не «відсутня»: її не видаляємо, навіть некоректну
          if (goneReplies[r.id]) return;                    // видалена кимось іще: не воскрешаємо
          if (typeof r.author !== 'string' || typeof r.text !== 'string') {   // колонки NOT NULL: один такий рядок валив би кожен save
            if (!badWarned[r.id]) { badWarned[r.id] = true; warn('reply skipped (author/text are not strings)', r.id); }
            return;
          }
          var row = replyToRow(r, c.id, channel);
          if (writtenReplies[r.id] !== stable(row) && !seen[r.id]) { seen[r.id] = true; up.push(row); }
        });
      });
      /* Видаляємо лише те, що викликач БАЧИВ (fl.base: знімок writtenReplies у момент виклику save + те, що ніс попередній
         виклик): відповідь, що зʼявилась після виклику, ним не видалена — просто його список її не знав. */
      Object.keys(writtenReplies).forEach(function (id) {
        if (kept[replyOwner[id]] && !have[id] && !goneReplies[id] && (fl.base[id] || retryDel[id])) del.push(id);
      });
      return { up: up, del: del, block: false };
    }

    function doSave(comments, fl) {
      var dropped = false;
      var keep = function (c) { if (gone[c.id]) { dropped = true; fl.dropped = true; return false; } return true; };
      comments = comments.filter(keep);          // видалене колегою не воскрешаємо, навіть якщо коментатор тримає його як _pending
      var rows = comments.map(function (c) { return commentToRow(c, channel); });
      /* Запис РІЗНИЦЕЮ (Deai 0.27.0): лише рядки, яких база ще не має в такому вигляді. Застарілий список одного вікна вже не
         перетирає чужого закриття чи доручення в РЕШТІ рядків; два записи в ОДИН рядок — виграє останній. Відповіді (0.34) — та
         сама різниця, окремо: нова відповідь до незмінного коментаря не чіпає `comments`. */
      var changed = rows.filter(function (r) { return written[r.id] !== stable(r); });
      var plan = planReplies(comments, fl);
      if (!changed.length && !plan.up.length && !plan.del.length && !plan.block) {
        cache = comments.slice(); seq++;
        var back0 = reattachForeign(fl, carriedIds(comments));
        syncSnap(); if (dropped || back0) emit(); return Promise.resolve();
      }
      var pre = changed.length && seeded && !freshRead ? precheck(changed) : Promise.resolve({ rows: changed, gone: [] });
      return pre.then(function (chk) {
        if (chk.gone.length) {
          chk.gone.forEach(function (id) { gone[id] = true; delete written[id]; });
          comments = comments.filter(keep);
        }
        var out = chk.rows;
        plan = planReplies(comments, fl);
        if (!out.length && !plan.up.length && !plan.del.length && !plan.block) {
          cache = comments.slice(); seq++;
          var back1 = reattachForeign(fl, carriedIds(comments));
          syncSnap(); if (dropped || back1) emit(); return null;
        }
        /* Порядок: коментарі, потім upsert відповідей, потім видалення відповідей. Відмова коментарів — далі не йдемо. */
        var res = { out: out, err: null, plan: plan, upDone: false, delDone: [], repErr: null };
        var step = out.length ? upsert(out, 0, TABLE) : Promise.resolve(null);
        return step.then(function (err) {
          res.err = err;
          if (err || !plan.up.length) return null;
          return upsert(plan.up, 0, REPLIES).then(function (e) { if (e) res.repErr = e; else res.upDone = true; return null; },
            function (e) { res.repErr = e || { message: 'rejected' }; return null; });
        }).then(function () {
          if (res.err || res.repErr || !plan.del.length) return null;
          var chunks = [];
          for (var i = 0; i < plan.del.length; i += 100) chunks.push(plan.del.slice(i, i + 100));
          return chunks.reduce(function (p, chunk) {
            return p.then(function () {
              if (res.repErr) return null;
              return raced(function () { return client.from(REPLIES).delete().in('id', chunk).eq('project_id', channel); }).then(function (r) {
                if (r && r.error) res.repErr = r.error; else res.delDone = res.delDone.concat(chunk);
                return null;
              }, function (e) { res.repErr = e || { message: 'rejected' }; return null; });   // відхилений проміс = помилка цієї пачки
            });
          }, Promise.resolve());
        }).then(function () {
          if (!res.err && !res.repErr && plan.block) {
            res.repErr = { message: 'replies unavailable' };
            scheduleFetch();                 // збій міг минути: перечитати, щоб відповіді знову запрацювали
          }
          return res;
        });
      }).then(function (res) {
        if (!res) return;
        var out = res.out, err = res.err;
        cache = comments.slice();            // оптимістичний кеш: запис не губиться, навіть якщо база не відповіла
        seq++;                               // а відповідь, що вже летіла до запису, його не затре
        if (!err) {
          var adopted = false, mergedBy = {};
          out.forEach(function (r) {
            var mine = null;
            for (var k = 0; k < changed.length; k++) if (changed[k].id === r.id) mine = changed[k];
            if (mine && stable(r) !== stable(mine)) { mergedBy[r.id] = r; adopted = true; }
          });
          if (adopted) {
            cache = cache.map(function (c) {
              if (!mergedBy[c.id]) return c;
              var rc = rowToComment(mergedBy[c.id]);
              if (c.replies) rc.replies = c.replies;     // відповіді живуть окремо від рядка коментаря: злиття їх не торкається
              return rc;
            });
          }
          out.forEach(function (r) { written[r.id] = stable(r); });
          if (res.upDone) res.plan.up.forEach(function (r) { writtenReplies[r.id] = stable(r); replyOwner[r.id] = r.comment_id; });
          res.delDone.forEach(function (id) { delete writtenReplies[id]; delete replyOwner[id]; delete retryDel[id]; });
          res.plan.del.forEach(function (id) { if (res.delDone.indexOf(id) < 0) retryDel[id] = true; });
          var back2 = reattachForeign(fl, carriedIds(comments));
          syncSnap();
          if (adopted || dropped || back2) emit();    // споживачі беруть злитий стан (чужа зміна не губиться, видалене зникає)
          if (res.repErr) { warn('replies save failed', res.repErr); throw new Error('supabase replies save failed: ' + res.repErr.message); }
          return;
        }
        res.plan.del.forEach(function (id) { retryDel[id] = true; });
        if (reattachForeign(fl, carriedIds(comments))) emit();
        warn('save failed after retries', err);
        throw new Error('supabase save failed: ' + err.message);
      });
    }

    var store = {
      ready: ready,
      get loadError() { return loadError; },
      /* Відповіді (0.34): `supportsReplies` — таблиця comment_replies є й читається; `repliesDown` — null чи причина
         ('no-replies-schema' | текст помилки). Подвійне сховище бере їх звідси. */
      get supportsReplies() { return supportsReplies; },
      get repliesDown() { return repliesDown; },
      load: function () { return cache; },
      /* Перечитування (його кличе «Огляд» при поверненні на нього). У межах TTL знімка мережі не торкається: компроміс —
         зміна колеги, що потрапила рівно в проміжок між перезавантаженнями рамки, зʼявиться до 2 хв із запізненням; решту
         закриває realtime. Поза TTL (чи без знімка) — повне читання. */
      refresh: function () { return fresh() ? Promise.resolve() : fetchAll(); },
      /* Живі оновлення: CommentLayer підписується тут; realtime → fetchAll → emit. */
      subscribe: function (fn) { if (typeof fn === 'function') listeners.push(fn); },
      /* Власні save йдуть ЧЕРГОЮ: цільова звірка додає круг до бази, і без черги старіший запис міг би дійти після новішого й
         лишити в базі старий текст. `changed` і звірка рахуються в момент виконання, проти `written`, що лишив попередній save;
         відмова одного не ламає черги, а промис кожного виклику — його власний. Запис, що стоїть у черзі за повільним, починається
         лише після нього; якщо рамка вивантажиться раніше, його надішле з браузерної копії `_pending` коментатора наступне
         завантаження. Після save, що відкинув видалене колегою, ще раз повідомляємо на наступному тіку: перше сповіщення
         йшло, поки пін ще `_pending`, і коментатор лишив би його на екрані. */
      save: function (comments) {
        var fl = { dropped: false };
        /* Базова лінія ВИКЛИКУ (синхронно, до черги): що бачив викликач — відповіді, відомі базі зараз, і ті, що ніс попередній
           виклик (він міг іще не дійти до writtenReplies). Видаляти save може лише це. */
        var base = keysOf(writtenReplies);
        Object.keys(lastCarried).forEach(function (id) { base[id] = true; });
        Object.keys(retryDel).forEach(function (id) { base[id] = true; });
        fl.base = base;
        lastCarried = carriedIds(comments);
        var p = chain.then(function () { return doSave(comments, fl); });
        var after = function () { if (fl.dropped && !closed) setTimeout(function () { if (!closed) emit(); }, 0); };
        chain = p.then(after, after);
        return p;
      },
      /* Жорстке видалення: upsert-збереження рядків не прибирає, тож видалення — окремий шлях. */
      remove: function (ids) {
        if (!ids || !ids.length) return Promise.resolve();
        /* Спершу відповіді (по 10 коментарів на запит — під сторожем «≤ 100 рядків на DELETE»); збій тут коментар не блокує:
           осиротіла відповідь нешкідлива. Далі — коментарі, як і раніше. */
        var pre = Promise.resolve();
        if (supportsReplies) {
          var chunks = [];
          for (var i = 0; i < ids.length; i += 10) chunks.push(ids.slice(i, i + 10));
          pre = chunks.reduce(function (p, chunk) {
            return p.then(function () {
              return raced(function () { return client.from(REPLIES).delete().in('comment_id', chunk).eq('project_id', channel); })
                .then(function (r) { return r && r.error ? r.error : null; }, function (e) { return e || 'failed'; })
                .then(function (err) {
                  if (!err) return null;
                  /* Сторож БД (≤ 100 рядків на DELETE) відхиляє весь запит, якщо в цих коментарів разом понад 100 відповідей:
                     видаляємо відомі адаптеру id відповідей пачками по ≤100. Збій і тут коментар не блокує. */
                  warn('replies delete failed', err);
                  var known = Object.keys(replyOwner).filter(function (rid) { return chunk.indexOf(replyOwner[rid]) >= 0; });
                  var parts = [];
                  for (var j = 0; j < known.length; j += 100) parts.push(known.slice(j, j + 100));
                  return parts.reduce(function (q, part) {
                    return q.then(function () {
                      return raced(function () { return client.from(REPLIES).delete().in('id', part).eq('project_id', channel); })
                        .then(function (r2) { if (r2 && r2.error) warn('replies delete by id failed', r2.error); }, function (e) { warn('replies delete by id failed', e); });
                    });
                  }, Promise.resolve());
                });
            });
          }, Promise.resolve());
        }
        /* Відомі відповіді цих коментарів — надгробки: застарілий save із черги їх не воскресить. */
        Object.keys(replyOwner).forEach(function (rid) { if (ids.indexOf(replyOwner[rid]) >= 0) goneReplies[rid] = true; });
        return pre.then(function () {
          return Promise.resolve(client.from(TABLE).delete().in('id', ids).eq('project_id', channel));
        }).then(function (res) {
          if (res.error) warn('delete failed', res.error);
          else ids.forEach(function (id) { gone[id] = true; });   // `remove` поза чергою save: без цього застарілий save воскресив би коментар
          cache = cache.filter(function (c) { return ids.indexOf(c.id) < 0; });
          ids.forEach(function (id) { delete written[id]; });
          Object.keys(replyOwner).forEach(function (rid) { if (ids.indexOf(replyOwner[rid]) >= 0) { delete writtenReplies[rid]; delete replyOwner[rid]; } });
          seq++;
          if (!res.error) syncSnap();
        });
      },
      close: function () {
        if (closed) return;
        closed = true;
        listeners.length = 0;
        if (catchTimer !== null) { clearTimeout(catchTimer); catchTimer = null; }
        if (refetchTimer !== null) { clearTimeout(refetchTimer); refetchTimer = null; }
        netPending.slice().forEach(function (abort) { abort('closed'); });
        /* removeChannel лише залишає канал; сокет realtime (з серцебиттям) закриває `disconnect`. Обидва — без відмов назовні. */
        var left;
        try { left = Promise.resolve(client.removeChannel(realtime)); } catch (e) { left = Promise.resolve(); }
        var left2 = Promise.resolve();
        if (repliesRealtime !== null) { try { left2 = Promise.resolve(client.removeChannel(repliesRealtime)); } catch (e) { left2 = Promise.resolve(); } }
        left.catch(function () { /* вже знято */ })
          .then(function () { return left2.catch(function () { /* вже знято */ }); })
          .then(function () { return client.realtime.disconnect(); })
          .catch(function () { /* вже закрито */ });
      }
    };
    if (bucket) store.uploadShot = uploadShot;
    return store;
  }

  window.DeaiComments = { create: create };
})();
