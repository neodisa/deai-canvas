/*!
 * Local file storage adapter for comment-layer (Design Canvas «Локальні · мені»).
 * НЕ Supabase: коментарі-фідбек Claude живуть у локальному файлі задачі через
 * ендпоінт сервера канваса (GET/POST /api/local-comments). Реалізує той самий
 * контракт сховища, що й supabase-adapter: { ready, load, subscribe, save, remove }.
 * Attaches window.CommentLayerLocal. Serializable fields only (drops _el/_pending).
 */
(function () {
  /* Відповіді піна (0.35). Запис зі строковим `id` зводиться до відомих полів;
     запис БЕЗ `id` — спадок від попередника (формат невідомий) — лишається
     дослівно, його ні губити, ні переписувати не можна. Не-обʼєкти відкидаємо. */
  function cleanReplies(rs) {
    if (!Array.isArray(rs)) return null;
    var out = [];
    for (var i = 0; i < rs.length; i++) {
      var r = rs[i];
      if (!r || typeof r !== 'object' || Array.isArray(r)) continue;
      if (typeof r.id !== 'string') { out.push(JSON.parse(JSON.stringify(r))); continue; }
      var o = { id: r.id };
      if (r.author !== undefined) o.author = r.author;
      if (r.text !== undefined) o.text = r.text;
      if (r.ts !== undefined) o.ts = r.ts;
      if (r.editedTs !== undefined) o.editedTs = r.editedTs;
      if (r.agent === true) o.agent = true;
      out.push(o);
    }
    return out.length ? out : null;
  }
  function clean(list) {
    return (list || []).map(function (c) {
      var o = {
        id: c.id, author: c.author, text: c.text, status: c.status, fp: c.fp,
        htmlSnapshot: c.htmlSnapshot || null, meta: c.meta || null,
        bornV: c.bornV, resolvedV: c.resolvedV || null,
        resolveReason: c.resolveReason || null, ts: c.ts || null,
      };
      var rs = cleanReplies(c.replies);
      if (rs) o.replies = rs;
      return o;
    });
  }
  /* `ДД.ММ.РРРР ГГ:ХХ` → `РРРРММДДГГХХ`; не розібралось — null. */
  function tsKey(ts) {
    var m = /^(\d{2})\.(\d{2})\.(\d{4}) (\d{2}):(\d{2})$/.exec(String(ts));
    return m ? m[3] + m[2] + m[1] + m[4] + m[5] : null;
  }
  function replyList(v) { return Array.isArray(v) ? v : []; }
  /* ⛔ ЗЛИТТЯ ВІДПОВІДЕЙ ПО id (0.35, спека §1). `S` — на сервері (там міг дописати
     агент), `W` — що вкладка знала, `M` — що вкладка шле. Узагальнене «поле
     змінила вкладка → бери її» тут не годиться: воно б стерло відповідь агента. */
  function mergeReplies(S, W, M) {
    S = replyList(S); W = replyList(W); M = replyList(M);
    var legacy = [], sById = {}, wById = {}, mById = {}, order = [], seen = {}, i, r;
    function isId(x) { return x && typeof x.id === 'string'; }
    for (i = 0; i < S.length; i++) {
      r = S[i];
      if (!r || typeof r !== 'object') continue;
      /* Спадок (без id) беремо лише з S: вкладка тримає його тільки те, що сама отримала з диска. */
      if (!isId(r)) { legacy.push(r); continue; }
      sById[r.id] = r;
      if (!seen[r.id]) { seen[r.id] = 1; order.push(r.id); }
    }
    for (i = 0; i < W.length; i++) if (isId(W[i])) wById[W[i].id] = W[i];
    for (i = 0; i < M.length; i++) {
      if (!isId(M[i])) continue;
      mById[M[i].id] = M[i];
      if (!seen[M[i].id]) { seen[M[i].id] = 1; order.push(M[i].id); }
    }
    var kept = [];
    for (i = 0; i < order.length; i++) {
      var id = order[i], mine = mById[id], was = wById[id], srv = sById[id], pick;
      if (mine) pick = (!was || !same(was, mine)) ? mine : srv;                   // знала й не міняла: бере серверну; на диску нема — видалили там
      else if (was) pick = null;                              // вкладка прибрала
      else pick = srv;                                        // чужа, вкладка не знала
      if (pick) kept.push(pick);
    }
    var keys = kept.map(function (x) { return tsKey(x.ts); });
    if (keys.every(function (k) { return k !== null; })) {
      var idx = kept.map(function (x, n) { return { x: x, k: keys[n], n: n }; });
      idx.sort(function (a, b) { return a.k < b.k ? -1 : a.k > b.k ? 1 : a.n - b.n; });
      kept = idx.map(function (e) { return e.x; });
    }
    return legacy.concat(kept);
  }
  /* ⛔ ЗНІМОК — окремі обʼєкти, яких шар не торкався і не торкнеться.
     Шар кладе отримане від адаптера у `this.comments` і вішає на піни `c._el`
     (DOM-вузол якоря), а на React-сторінці вузол через `__reactFiber$…` →
     `stateNode` замикається в кільце. Тому все, що адаптер серіалізує або
     тримає як базу злиття, — лише знімок, а шару йдуть окремі копії
     (fb 05.11.2026, `portfolio`: `JSON.stringify` падав, POST не йшов). */
  function snap(list) { return JSON.parse(JSON.stringify(clean(list))); }
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
      if (k === 'meta' || k === 'replies') continue;
      var mine = STATUS_GROUP.indexOf(k) >= 0 ? group : !same(w[k], m[k]);
      if (mine) out[k] = m[k];
    }
    if (!same(w.replies, m.replies)) {            // не міняла — лишаються серверні сирі
      var rs = mergeReplies(s.replies, w.replies, m.replies);
      if (rs.length) out.replies = rs; else delete out.replies;
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
    /* ⛔ ЗАПИСИ ПО ЧЕРЗІ. Коментатор у `removeComment` кличе `remove([id])` і
       одразу `save(list)`, не чекаючи першого. Обидва GET приходили ДО обох
       POST: злиття `save` бачило пін на сервері, не бачило у вкладці — «не
       чіпала» — і повертало видалений. Виграв той POST, що ліг останнім
       (fb 05.11.2026). Кожен запис тепер стартує після попереднього, тож його
       GET бачить уже записане. Невдача одного черги не зупиняє. */
    var queue = Promise.resolve();
    function serial(job) {
      var p = queue.then(job);
      queue = p.catch(function () {});
      return p;
    }
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
        /* Шару — копія без `clean`: чужі поля піна (`replies` від Клода) він
           має бачити, як бачив до цього; базі — знімок у формі `clean`. */
        base = snap(list); cache = JSON.parse(JSON.stringify(list)); notify();
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
    /* `cache` і `base` — РІЗНІ масиви: шар дописує новий пін прямо в масив
       із `load()`, і коли це був масив бази, новий пін вважався «видаленим
       іншою вкладкою» (рятував його досі лише `_el`, що робив рядки різними). */
    var ready = fetchServer()
      .then(function (rows) { base = snap(rows); cache = rows; notify(); })
      .catch(function () { cache = []; base = []; });
    return {
      ready: ready,
      load: function () { return cache; },
      /* Перечитати файл зараз. Цей адаптер не опитує сервер сам, тож без цього
         вкладка «Огляду» не бачила пінів, лишених у живому виді (ревʼю T-45, D2). */
      refresh: function () {
        return fetchServer().then(function (rows) { base = snap(rows); cache = rows; notify(); });
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
        var sent = snap(next);                        // шар зараз обвішає `next` якорями
        cache = next; notify();                       // UI не мусить чекати мережі
        return serial(function () { return mergeThenWrite(sent, known); });
      },
      /* `remove` — ЯВНИЙ намір, на відміну від «пін просто відсутній у моєму
         знімку». Тому тут злиття не потрібне: беремо серверний список і
         викидаємо саме названі id. */
      remove: function (ids) {
        cache = cache.filter(function (c) { return ids.indexOf(c.id) < 0; });
        notify();
        return serial(function () {
          return fetchServer().then(function (server) {
            return write(server.filter(function (c) { return ids.indexOf(c.id) < 0; }));
          }, function () { return write(snap(cache)); });
        });
      },
    };
  }
  if (typeof window !== 'undefined') window.CommentLayerLocal = LocalStore;
})();
