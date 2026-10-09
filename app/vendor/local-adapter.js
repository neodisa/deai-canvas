/*!
 * Local file storage adapter for comment-layer (Design Canvas «Локальні · мені»).
 * НЕ Supabase: коментарі-фідбек Claude живуть у локальному файлі задачі через
 * ендпоінт сервера канваса (GET/POST /api/local-comments). Реалізує той самий
 * контракт сховища, що й supabase-adapter: { ready, load, subscribe, save, remove }.
 * Attaches window.CommentLayerLocal. Serializable fields only (drops _el/_pending).
 */
(function () {
  function clean(list) {
    return (list || []).map(function (c) {
      return {
        id: c.id, author: c.author, text: c.text, status: c.status, fp: c.fp,
        htmlSnapshot: c.htmlSnapshot || null, meta: c.meta || null,
        bornV: c.bornV, resolvedV: c.resolvedV || null,
        resolveReason: c.resolveReason || null, ts: c.ts || null,
      };
    });
  }
  function byId(list) {
    var m = {};
    for (var i = 0; i < (list || []).length; i++) m[list[i].id] = list[i];
    return m;
  }
  /* Поля, що міняються РАЗОМ: закриття — це статус + ітерація + причина (+ мітка
     `meta.resolvedAt`). Узяти статус з одного боку, а причину з іншого означало б
     «відкритий пін із причиною закриття». */
  var STATUS_GROUP = ['status', 'resolvedV', 'resolveReason'];
  function same(a, b) { return JSON.stringify(a) === JSON.stringify(b); }
  /* ⛔ ЗЛИТТЯ ПО ПОЛЯХ (fb-30092026-423d00). `s` — серверний пін у СИРІЙ формі,
     `w` — що вкладка знала (`clean`), `m` — що вкладка шле (`clean`). Поле, якого
     вкладка не міняла, береться з сервера. Злиття цілим піном програвало
     переякоренню: коментатор після правки макета перераховує `fp` усім своїм
     відкритим пінам, і пін, закритий з диска, повертався відкритим. */
  function mergePin(s, w, m) {
    var out = {}, k;
    for (k in s) out[k] = s[k];
    var group = STATUS_GROUP.some(function (f) { return !same(w[f], m[f]); });
    for (k in m) {
      if (k === 'meta') continue;
      var mine = STATUS_GROUP.indexOf(k) >= 0 ? group : !same(w[k], m[k]);
      if (mine) out[k] = m[k];
    }
    if (!same(w.meta, m.meta) || group) out.meta = mergeMeta(s.meta, w.meta, m.meta, group);
    return out;
  }
  function mergeMeta(sm, wm, mm, group) {
    if (mm == null && wm != null) return null;            // вкладка прибрала meta цілком
    var out = {}, k;
    sm = sm || {}; wm = wm || {}; mm = mm || {};
    for (k in sm) out[k] = sm[k];
    var keys = {};
    for (k in wm) keys[k] = 1;
    for (k in mm) keys[k] = 1;
    for (k in keys) {
      var mine = k === 'resolvedAt' ? group : !same(wm[k], mm[k]);
      if (!mine) continue;
      if (k in mm) out[k] = mm[k]; else delete out[k];
    }
    return out;
  }

  function LocalStore(opts) {
    var endpoint = (opts && opts.endpoint) || '/api/local-comments';
    var cache = [];
    /* БАЗА злиття: що ця вкладка ЗНАЛА на момент останнього узгодження з
       сервером. Саме вона дає різницю між «клієнт змінив пін» і «клієнт про
       пін не в курсі» — сервер із повного масиву цього не бачить. */
    var base = [];
    var subs = [];
    function notify() { for (var i = 0; i < subs.length; i++) { try { subs[i](cache); } catch (e) {} } }
    function fetchServer() {
      return fetch(endpoint)
        .then(function (r) { return r.json(); })
        .then(function (d) { return (d && d.comments) || []; });
    }
    function write(list) {
      return fetch(endpoint, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ comments: list }),
      }).then(function (r) {
        if (!r.ok) throw new Error('local save failed');
        cache = list; base = list.map(function (c) { return c; }); notify();
      });
    }
    /* ⛔ ТРЬОХСТОРОННЄ ЗЛИТТЯ ПЕРЕД ЗАПИСОМ.
       Шар тримає весь список у памʼяті і POSTить його ЦІЛКОМ, а ендпоінт
       замінює файл. Через це закриття пінів із боку Клода відкочувалось:
       дизайнер додавав пін зі сторінки, відкритої ДО закриття, і всі закриті
       ставали відкритими знову (фідбек 08.09.2026). Тепер серверний список
       береться за основу, а накладається на нього тільки те, що вкладка
       СПРАВДІ змінила відносно своєї бази. Ні `updated_at`, ні ревізій у пінах
       немає — і вигадувати їх не довелось. З 1.47 — по полях, а не цілим піном
       (fb-30092026-423d00, `mergePin`). */
    function mergeThenWrite(list, known) {
      return fetchServer().then(function (server) {
        /* База й знімок вкладки — в ОДНІЙ формі (`clean`): файл міг записати
           не цей адаптер (інша форма, інший порядок ключів), і тоді кожен пін
           здавався б «зміненим вкладкою» — повертались і воскресіння, і відкат
           закриття Клодом (повторне ревʼю T-45, D2). */
        var was = byId(clean(known));
        var mine = byId(list);
        var out = [];
        for (var i = 0; i < server.length; i++) {
          var s = server[i];
          var m = mine[s.id];
          if (!m) { out.push(s); continue; }          // вкладка цього не чіпала
          var changed = JSON.stringify(was[s.id]) !== JSON.stringify(m);
          out.push(changed ? mergePin(s, was[s.id] || {}, m) : s);   // виграють лише ЇЇ поля
        }
        var have = byId(out);
        for (var j = 0; j < list.length; j++) {
          var c = list[j];
          if (have[c.id]) continue;
          /* Сервер цього піна не має. Новий він лише тоді, коли його не було й
             у БАЗІ вкладки. Був і не змінений — його видалила ІНША вкладка
             («Огляд» і живий вид пишуть в один файл): не воскрешаємо
             (ревʼю T-45, D2). Був і змінений тут — правка вкладки виграє. */
          var old = was[c.id];
          if (!old || JSON.stringify(old) !== JSON.stringify(c)) out.push(c);
        }
        return write(out);
      }, function () { return write(list); });        // сервер не відповів — як раніше
    }
    var ready = fetchServer()
      .then(function (rows) { cache = rows; base = rows; notify(); })
      .catch(function () { cache = []; base = []; });
    return {
      ready: ready,
      load: function () { return cache; },
      /* Перечитати файл зараз. Цей адаптер не опитує сервер сам, тож без цього
         вкладка «Огляду» не бачила пінів, лишених у живому виді (ревʼю T-45, D2). */
      refresh: function () {
        return fetchServer().then(function (rows) { cache = rows; base = rows; notify(); });
      },
      close: function () { subs.length = 0; },   // інстанс знищено — сповіщати нікого
      subscribe: function (f) { if (typeof f === 'function') subs.push(f); },
      save: function (list) {
        var next = clean(list);
        /* База — та, яку вкладка ЗНАЛА, коли породила цей список, а не та, що
           буде на момент відповіді сервера. Два save() внахлест: GET другого
           приходить уже ПІСЛЯ запису першого, база «закрито», а список вкладки
           ще «відкрито» — і злиття проти свіжої бази прочитало б це як «вкладка
           відкрила пін» (ревʼю батча 1.47, D2). */
        var known = base;
        cache = next; notify();                       // UI не мусить чекати мережі
        return mergeThenWrite(next, known);
      },
      /* `remove` — ЯВНИЙ намір, на відміну від «пін просто відсутній у моєму
         знімку». Тому тут злиття не потрібне: беремо серверний список і
         викидаємо саме названі id. */
      remove: function (ids) {
        cache = cache.filter(function (c) { return ids.indexOf(c.id) < 0; });
        notify();
        return fetchServer().then(function (server) {
          return write(server.filter(function (c) { return ids.indexOf(c.id) < 0; }));
        }, function () { return write(cache); });
      },
    };
  }
  if (typeof window !== 'undefined') window.CommentLayerLocal = LocalStore;
})();
