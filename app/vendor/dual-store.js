/*!
 * Комбіноване сховище коментарів Deai (0.27.0, етап Б2): локальний файл задачі (фідбек Claude) + командний канал модуля
 * ролі `comments` — ОДИН контракт сховища comment-layer: { ready, load, save, remove, subscribe, refresh, close, uploadShot }.
 * Адресат піна — СХОВИЩЕ, де він лежить (спека Б-Р5). Коментатору — копії зі службовим `_aud` ('local' | 'project');
 * під-сховищам `_aud` не йде (адаптери однаково пишуть лише свій білий список). Пін без `_aud` — локальний: приватне
 * за замовчуванням, колегам випадково не поїде.
 * ⛔ Незмінну частину адресата не пишемо (поправка 6 плану Б2): інакше кожна дія з локальним піном переписувала б увесь
 *   командний список. ⛔ Тінь командної частини (поправка 7): локальний адаптер сповіщає синхронно ПІД ЧАС `save`, а
 *   командний — лише згодом (realtime), і обʼєднання взяло б старий командний кеш. ⛔ Скріншот — у командне сховище лише
 *   командного піна (поправка 5): скрін фідбеку для Claude не мусить лягти в публічний кошик колег.
 * Падіння командного (`team: null` + `teamDown`, або його `ready` відмовив) — локальне працює далі; причина — `teamDown`.
 * Attaches window.DeaiDualStore. Без DOM: тест — `tests/dual-store.test.mjs`.
 */
(function () {
  var FIELDS = ['id', 'author', 'text', 'status', 'fp', 'htmlSnapshot', 'meta', 'bornV', 'resolvedV', 'resolveReason', 'ts'];
  function strip(c) { var o = {}; for (var k in c) if (k !== '_aud') o[k] = c[k]; return o; }
  function tag(list, aud) {
    return (list || []).map(function (c) { var o = {}; for (var k in c) o[k] = c[k]; o._aud = aud; return o; });
  }
  function stable(v) {
    if (Array.isArray(v)) return '[' + v.map(stable).join(',') + ']';
    if (v && typeof v === 'object') {
      return '{' + Object.keys(v).filter(function (k) { return v[k] !== undefined; }).sort()
        .map(function (k) { return JSON.stringify(k) + ':' + stable(v[k]); }).join(',') + '}';
    }
    return JSON.stringify(v === undefined ? null : v);
  }
  /* Відбиток частини для «чи змінилась»: лише поля контракту, `null` замість відсутнього, порядок — за id. */
  function sig(list) {
    return stable((list || []).map(function (c) {
      var o = {}; for (var i = 0; i < FIELDS.length; i++) o[FIELDS[i]] = c[FIELDS[i]] == null ? null : c[FIELDS[i]];
      return o;
    }).sort(function (a, b) { return String(a.id) < String(b.id) ? -1 : String(a.id) > String(b.id) ? 1 : 0; }));
  }
  /* Синхронний кидок під-сховища → відмова проміса (а не виняток повз `Promise.all`); синхронність виклику зберігаємо. */
  function call(fn) { try { return Promise.resolve(fn()); } catch (e) { return Promise.reject(e); } }
  function has(list, id) { for (var i = 0; i < (list || []).length; i++) if (list[i] && list[i].id === id) return true; return false; }

  function DualStore(opts) {
    var local = opts.local;
    var team = opts.team || null;
    var subs = [];
    var teamDirty = false;                   // командний запис відхилено: кеші вже мають список, а база — ні; повторити
    var shadow = null;                       // командна частина, щойно віддана в `team.save`, поки `team` не заговорить сам
    var store = { teamDown: team ? null : String(opts.teamDown || 'team comments unavailable') };
    function teamList() { return team ? (shadow || team.load()) : []; }
    function union() { return tag(local.load(), 'local').concat(tag(teamList(), 'project')); }
    function notify() { var u = union(); for (var i = 0; i < subs.length; i++) { try { subs[i](u); } catch (e) {} } }
    function dropTeam(why) {
      if (team && typeof team.close === 'function') { try { team.close(); } catch (e) {} }
      team = null; shadow = null; store.teamDown = String(why || 'team comments unavailable');
    }
    if (typeof local.subscribe === 'function') local.subscribe(function () { notify(); });
    if (team && typeof team.subscribe === 'function') team.subscribe(function () { shadow = null; notify(); });
    store.ready = Promise.all([
      Promise.resolve(local.ready),
      team ? Promise.resolve(team.ready).catch(function (e) { dropTeam((e && e.message) || 'team comments did not answer'); }) : null,
    ]).then(function () {});
    store.load = function () { return union(); };
    store.save = function (list) {
      var mine = { local: [], project: [] };
      for (var i = 0; i < (list || []).length; i++) {
        var c = list[i]; if (!c) continue;
        mine[c._aud === 'project' ? 'project' : 'local'].push(strip(c));
      }
      var doLocal = sig(mine.local) !== sig(local.load());
      var doTeam = !!team && (teamDirty || sig(mine.project) !== sig(teamList()));
      /* Тінь — ДО локального запису: локальний адаптер сповіщає синхронно всередині `save`, і обʼєднання в тому
         сповіщенні мусить уже бачити нову командну частину (поправка 7). */
      if (doTeam) shadow = mine.project;
      /* `_aud` ставить лише коментатор при створенні піна, тож пін не мандрує між сховищами; якби міг — стару копію
         довелося б видаляти. */
      var jobs = [];
      if (doLocal) jobs.push(call(function () { return local.save(mine.local); }));
      if (doTeam) {
        jobs.push(call(function () { return team.save(mine.project); }).then(
          function () { teamDirty = false; },
          function (e) { teamDirty = true; throw e; }));
      }
      else if (!team && mine.project.length) {
        jobs.push(Promise.reject(new Error('team comments unavailable: ' + store.teamDown)));
      }
      return Promise.all(jobs).then(function () {});
    };
    store.remove = function (ids) {
      ids = ids || [];
      var l = [], t = [];
      /* id, що є в обох сховищах, видаляється з обох (id унікальні за генератором; суто теоретично). */
      for (var i = 0; i < ids.length; i++) {
        var inL = has(local.load(), ids[i]), inT = has(teamList(), ids[i]);
        if (inL || !inT) l.push(ids[i]);
        if (team && (inT || !inL)) t.push(ids[i]);
      }
      if (shadow) shadow = shadow.filter(function (c) { return t.indexOf(c.id) < 0; });
      var jobs = [];
      if (l.length && typeof local.remove === 'function') jobs.push(call(function () { return local.remove(l); }));
      if (t.length && typeof team.remove === 'function') jobs.push(call(function () { return team.remove(t); }));
      return Promise.all(jobs).then(function () {});
    };
    store.subscribe = function (f) { if (typeof f === 'function') subs.push(f); };
    store.refresh = function () {
      return Promise.all([
        typeof local.refresh === 'function' ? local.refresh() : null,
        team && typeof team.refresh === 'function' ? team.refresh() : null,
      ]).then(function () {});
    };
    /* Свіжість локальних (спека Б2.1): локальний адаптер живих оновлень не має, а агент пише в той самий файл
       (`inbox.py resolve`). Оболонка кличе це на `focus` свого вікна й на відкриття панелі; командне не чіпаємо (трафік). */
    store.refreshLocal = function () {
      return typeof local.refresh === 'function' ? Promise.resolve(local.refresh()).then(function () {}) : Promise.resolve();
    };
    store.close = function () {
      subs.length = 0;
      if (typeof local.close === 'function') { try { local.close(); } catch (e) {} }
      if (team && typeof team.close === 'function') { try { team.close(); } catch (e) {} }
    };
    store.uploadShot = function (id, dataUrl, c) {
      if (!team || typeof team.uploadShot !== 'function' || !c || c._aud !== 'project') return Promise.resolve(null);
      return Promise.resolve(team.uploadShot(id, dataUrl));
    };
    return store;
  }
  if (typeof window !== 'undefined') window.DeaiDualStore = DualStore;
})();
