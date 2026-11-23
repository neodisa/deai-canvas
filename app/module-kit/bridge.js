/* Bridge between a module panel and the Deai Canvas shell (classic script, no imports).
   The panel lives in a sandboxed iframe: no access to the shell or the network, only postMessage to the parent.
   Outgoing: {deai: 1, id, method, args}. Incoming, ONLY from window.parent with deai === 1:
   a reply {deai: 1, re, ok, value | error, detail} or an event {deai: 1, event, data}. */
(function () {
  "use strict";
  var win = window;
  var nextId = 1;
  /* Map, а не {}: імена подій і `re` приходять ззовні — `__proto__`/`constructor` не мають чіпати Object.prototype. */
  var pending = new Map();
  var subs = new Map();
  var MAX_PENDING = 64;
  var PENDING_MS = 60000;
  var readyResolve;
  var ready = new Promise(function (resolve) { readyResolve = resolve; });

  function post(id, method, args) {
    win.parent.postMessage({ deai: 1, id: id, method: method, args: args }, "*");
  }

  function request(method, args) {
    return new Promise(function (resolve, reject) {
      if (pending.size >= MAX_PENDING) {
        var busy = new Error("too many pending requests");
        busy.code = "busy";
        reject(busy);
        return;
      }
      var id = nextId++;
      var timer = win.setTimeout(function () {
        if (!pending.delete(id)) return;
        var err = new Error("no reply from the shell");
        err.code = "timeout";
        reject(err);
      }, PENDING_MS);
      pending.set(id, { resolve: resolve, reject: reject, timer: timer });
      post(id, method, args);
    });
  }

  function applyTheme(data) {
    if (!data || typeof data !== "object") return;
    var root = win.document.documentElement;
    var theme = data.theme;
    if (typeof theme === "string" && theme.length <= 20 && /^[a-z-]+$/.test(theme)) {
      root.dataset.theme = theme;
    }
    var vars = data.vars;
    if (vars && typeof vars === "object") {
      Object.keys(vars).forEach(function (key) {
        var value = vars[key];
        if (/^--[a-z0-9-]{1,60}$/.test(key) && typeof value === "string" && value.length <= 200) {
          root.style.setProperty(key, value);
        }
      });
    }
  }

  function emit(event, data) {
    if (event === "init" || event === "theme") applyTheme(data);
    if (event === "init") readyResolve(data);
    var list = subs.get(event);
    if (!list) return;
    list.slice().forEach(function (fn) {
      try { fn(data); } catch (e) { /* a throwing subscriber must not break the others */ }
    });
  }

  win.addEventListener("message", function (e) {
    if (e.source !== win.parent) return;
    var d = e.data;
    if (!d || d.deai !== 1) return;
    if (typeof d.re === "number" || typeof d.re === "string") {
      var p = pending.get(d.re);
      if (!p) return;
      pending.delete(d.re);
      win.clearTimeout(p.timer);
      if (d.ok === true) {
        p.resolve(d.value);
      } else {
        var err = new Error(d.detail || d.error);
        err.code = d.error;
        p.reject(err);
      }
      return;
    }
    if (typeof d.event === "string") emit(d.event, d.data);
  });

  win.deai = {
    ready: ready,
    hello: function () { return request("hello", []); },
    context: function () { return request("context", []); },
    selection: function () { return request("selection", []); },
    call: function (fn, args) { return request("call", [fn, args]); },
    toast: function (text) { post(nextId++, "toast", [text]); },
    close: function () { post(nextId++, "close", []); },
    on: function (event, fn) {
      if (typeof fn !== "function") return function () {};
      var cur = subs.get(event);
      if (!cur) { cur = []; subs.set(event, cur); }
      cur.push(fn);
      return function () {
        var list = subs.get(event) || [];
        var i = list.indexOf(fn);
        if (i >= 0) list.splice(i, 1);
      };
    }
  };

  win.deai.hello().catch(function () {});
})();
