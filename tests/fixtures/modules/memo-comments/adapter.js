/* memo-comments — браузерний адаптер ролі `comments` (еталон для авторів модулів, спека 2b-2).
 *
 * Реєструє фабрику сховища CommentLayer: `window.DeaiComments = { create(cfg) { … } }`.
 *   cfg = { …client_config модуля (тут: endpoint, pubkey), channel, onChange }
 * Сховище: { ready, load(), save(comments), remove(ids), subscribe(fn), close() }.
 * Маршрути сервісу — ті самі, що в server.py:
 *   GET  <endpoint>/c/<канал>          → масив коментарів
 *   POST <endpoint>/c/<канал>          ← {comments}  (upsert за id)
 *   POST <endpoint>/c/<канал>/remove   ← {ids}
 * Тіло йде як `text/plain`: так запит «простий» і не потребує CORS-preflight; сервіс мусить відповідати
 * `Access-Control-Allow-Origin` (сторінка канваса й опубліковане превʼю — інший origin).
 * `subscribe` опитує сервіс раз на секунду. Інших глобальних імен адаптер не створює. */
(function () {
  function create(cfg) {
    var base = String(cfg.endpoint).replace(/\/+$/, '') + '/c/' + encodeURIComponent(cfg.channel);
    var cache = [];
    var subs = [];
    var timer = null;
    var pending = 0;                       // записів у дорозі: опитування їх не перебиває

    function notify() {
      for (var i = 0; i < subs.length; i++) { try { subs[i](cache); } catch (e) { /* підписник не валить решту */ } }
      if (typeof cfg.onChange === 'function') { try { cfg.onChange(cache); } catch (e) { /* те саме */ } }
    }
    function get() {
      return fetch(base).then(function (r) {
        if (!r.ok) throw new Error('memo: load ' + r.status);
        return r.json();
      }).then(function (rows) { return Array.isArray(rows) ? rows : []; });
    }
    function post(tail, body) {
      pending++;
      var done = function () { pending--; };
      return fetch(base + tail, {
        method: 'POST',
        headers: { 'Content-Type': 'text/plain;charset=UTF-8' },
        body: JSON.stringify(body)
      }).then(function (r) {
        done();
        if (!r.ok) throw new Error('memo: save ' + r.status);
      }, function (e) { done(); throw e; });
    }
    function poll() {
      if (pending) return;
      get().then(function (rows) {
        if (pending || JSON.stringify(rows) === JSON.stringify(cache)) return;
        cache = rows;
        notify();
      }, function () { /* мережа — наступного разу */ });
    }

    var ready = get().then(function (rows) { cache = rows; }, function () { cache = []; });
    return {
      ready: ready,
      load: function () { return cache; },
      save: function (comments) {
        cache = comments.slice();
        notify();
        return post('', { comments: comments });
      },
      remove: function (ids) {
        cache = cache.filter(function (c) { return ids.indexOf(c.id) < 0; });
        notify();
        return post('/remove', { ids: ids });
      },
      subscribe: function (fn) {
        if (typeof fn !== 'function') return;
        subs.push(fn);
        if (!timer) timer = setInterval(poll, 1000);
      },
      close: function () { subs.length = 0; if (timer) { clearInterval(timer); timer = null; } }
    };
  }
  window.DeaiComments = { create: create };
})();
