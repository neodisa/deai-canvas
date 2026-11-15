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
 *     (скасовується будь-яким повним читанням чи `close()`; далі realtime підписаний без прогалини) — тож і зміна, що
 *     випала в проміжок між рамками, зʼявляється щонайбільше за 2 хв. Засіяний адаптер НЕ показує смугу «команда впала» для збою, що почався
 *     після знімка (`loadError` читає лише `checkLoad` дуал-сховища, раз після `ready`); записи й далі ретраяться через дуал-сховище. Запис ДО першого власного повного
 *     читання (`seeded && !freshRead`) не сліпий: `save` спершу питає в бази лише змінені id (`in('id', …)`) і зливає
 *     поле-за-полем (і ключ-за-ключем `meta`) трійкою база(`written`)/наше/їхнє; обидва змінили — наше (як до кешу).
 *     Знімок спільний для рамок вкладки: `syncSnap` пише, лише якщо `t` у сховищі — наш (інакше затер би новіше читання).
 *     Без `sessionStorage` (чи коли він кидає) адаптер поводиться як раніше. Сховище, що переживає вкладку, не використовується навмисно.
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
  var CACHE_TTL_MS = 120000;                 // вік знімка каналу в sessionStorage, до якого повного читання не потрібно
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

  /* Записати знімок {t, rows}. Завеликий — не зберігаємо й прибираємо старий; квота — чистимо всі наші ключі й одна повторна
     спроба; решту мовчки здаємо. Заодно вичищаємо чужі знімки старші за TTL. */
  function writeSnap(ss, key, t, rows) {
    try {
      var val = JSON.stringify({ t: t, rows: rows });
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
      writeSnap(ss, snapKey, o.t, cache.map(function (c) { return commentToRow(c, channel); }));
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
      var lost = function () { if (fromCatch === true) scheduleCatch(CACHE_TTL_MS); };
      return Promise.resolve(client.from(TABLE).select('*').eq('project_id', channel).order('id')).then(function (res) {
        if (closed || mine !== seq) { lost(); return; }
        if (res.error) { loadError = String(res.error.message || res.error); warn('fetch failed', res.error); lost(); return; }
        loadError = null;
        freshRead = true;
        if (catchTimer !== null) { clearTimeout(catchTimer); catchTimer = null; }   // повне читання вдалось: наздоганяти нічого
        (res.data || []).forEach(function (r) { delete gone[r.id]; });
        cache = (res.data || []).map(rowToComment);
        written = {};
        cache.forEach(function (c) { written[c.id] = stable(commentToRow(c, channel)); });
        if (ss) { snapT = Date.now(); writeSnap(ss, snapKey, snapT, res.data || []); }
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
      if (snap && age >= 0 && age < CACHE_TTL_MS) {
        cache = snap.rows.map(rowToComment);
        cache.forEach(function (c) { written[c.id] = stable(commentToRow(c, channel)); });
        snapT = snap.t;
        seeded = true;
        /* Наздоганяюче читання: без нього засіяний екземпляр не побачив би зміни, що сталась, коли в вкладці ніхто не слухав
           realtime (проміжок між рамками, чи користувач був на іншій задачі). Одне, на кінець життя знімка. */
        catchTimer = setTimeout(function () { catchTimer = null; fetchAll(true); }, CACHE_TTL_MS - age);
      }
    }
    var ready = seeded ? Promise.resolve().then(function () { if (!closed) emit(); }) : fetchAll();

    function upsert(rows, attempt) {
      return Promise.resolve(client.from(TABLE).upsert(rows, { onConflict: 'id' })).then(function (res) {
        if (!res.error) return null;
        if (attempt + 1 >= ATTEMPTS) return res.error;
        return sleep(300 * (attempt + 1)).then(function () { return upsert(rows, attempt + 1); });
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
      return Promise.resolve().then(function () { return client.from(TABLE).select('*').in('id', ids).eq('project_id', channel); }).then(function (res) {
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

    function doSave(comments) {
      var dropped = false;
      var keep = function (c) { if (gone[c.id]) { dropped = true; return false; } return true; };
      comments = comments.filter(keep);          // видалене колегою не воскрешаємо, навіть якщо коментатор тримає його як _pending
      var rows = comments.map(function (c) { return commentToRow(c, channel); });
      /* Запис РІЗНИЦЕЮ (Deai 0.27.0): лише рядки, яких база ще не має в такому вигляді. Застарілий список одного вікна вже не
         перетирає чужого закриття чи доручення в РЕШТІ рядків; два записи в ОДИН рядок — виграє останній. */
      var changed = rows.filter(function (r) { return written[r.id] !== stable(r); });
      if (!changed.length) { cache = comments.slice(); seq++; syncSnap(); if (dropped) emit(); return Promise.resolve(); }
      var pre = seeded && !freshRead ? precheck(changed) : Promise.resolve({ rows: changed, gone: [] });
      return pre.then(function (chk) {
        if (chk.gone.length) {
          chk.gone.forEach(function (id) { gone[id] = true; delete written[id]; });
          comments = comments.filter(keep);
        }
        var out = chk.rows;
        if (!out.length) { cache = comments.slice(); seq++; syncSnap(); if (dropped) emit(); return null; }
        return upsert(out, 0).then(function (err) { return [out, err]; });
      }).then(function (pair) {
        if (!pair) return;
        var out = pair[0], err = pair[1];
        cache = comments.slice();            // оптимістичний кеш: запис не губиться, навіть якщо база не відповіла
        seq++;                               // а відповідь, що вже летіла до запису, його не затре
        if (!err) {
          var adopted = false, mergedBy = {};
          out.forEach(function (r) {
            var mine = null;
            for (var k = 0; k < changed.length; k++) if (changed[k].id === r.id) mine = changed[k];
            if (mine && stable(r) !== stable(mine)) { mergedBy[r.id] = r; adopted = true; }
          });
          if (adopted) cache = cache.map(function (c) { return mergedBy[c.id] ? rowToComment(mergedBy[c.id]) : c; });
          out.forEach(function (r) { written[r.id] = stable(r); });
          syncSnap();
          if (adopted || dropped) emit();    // споживачі беруть злитий стан (чужа зміна не губиться, видалене зникає)
          return;
        }
        warn('save failed after retries', err);
        throw new Error('supabase save failed: ' + err.message);
      });
    }

    var store = {
      ready: ready,
      get loadError() { return loadError; },
      load: function () { return cache; },
      /* Перечитування (його кличе «Огляд» при поверненні на нього). У межах TTL знімка мережі не торкається: компроміс —
         зміна колеги, що потрапила рівно в проміжок між перезавантаженнями рамки, зʼявиться до 2 хв із запізненням; решту
         закриває realtime. Поза TTL (чи без знімка) — повне читання. */
      refresh: function () { return fresh() ? Promise.resolve() : fetchAll(); },
      /* Живі оновлення: CommentLayer підписується тут; realtime → fetchAll → emit. */
      subscribe: function (fn) { if (typeof fn === 'function') listeners.push(fn); },
      /* Власні save йдуть ЧЕРГОЮ: цільова звірка додає круг до бази, і без черги старіший запис міг би дійти після новішого й
         лишити в базі старий текст. `changed` і звірка рахуються в момент виконання, проти `written`, що лишив попередній save;
         відмова одного не ламає черги, а промис кожного виклику — його власний. */
      save: function (comments) {
        var p = chain.then(function () { return doSave(comments); });
        chain = p.catch(function () { /* черга йде далі */ });
        return p;
      },
      /* Жорстке видалення: upsert-збереження рядків не прибирає, тож видалення — окремий шлях. */
      remove: function (ids) {
        if (!ids || !ids.length) return Promise.resolve();
        return Promise.resolve(client.from(TABLE).delete().in('id', ids).eq('project_id', channel)).then(function (res) {
          if (res.error) warn('delete failed', res.error);
          cache = cache.filter(function (c) { return ids.indexOf(c.id) < 0; });
          ids.forEach(function (id) { delete written[id]; });
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
