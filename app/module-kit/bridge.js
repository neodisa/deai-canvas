/* Bridge between a module panel and the Deai Canvas shell (classic script, no imports).
   The panel lives in a sandboxed iframe: no access to the shell or the network, only postMessage to the parent.
   Outgoing: {deai: 1, id, method, args}. Incoming, ONLY from window.parent with deai === 1:
   a reply {deai: 1, re, ok, value | error, detail} or an event {deai: 1, event, data}.
   deai.page.* proxies the page helper (needs the "page" permissions); pick() has no timeout: the shell resolves it with null when the panel closes.
   Esc inside the panel while a pick is pending cancels it (the key never reaches the canvas from the sandboxed panel). */
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

  function request(method, args, ms) {
    return new Promise(function (resolve, reject) {
      if (pending.size >= MAX_PENDING) {
        var busy = new Error("too many pending requests");
        busy.code = "busy";
        reject(busy);
        return;
      }
      var id = nextId++;
      var timer = ms === 0 ? 0 : win.setTimeout(function () {
        if (!pending.delete(id)) return;
        var err = new Error("no reply from the shell");
        err.code = "timeout";
        reject(err);
      }, ms || PENDING_MS);
      pending.set(id, { resolve: resolve, reject: reject, timer: timer, method: method, cancelled: false });
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

  /* Esc in the panel during a pending pick: ask the shell to cancel it, once per pick. Other keys are left alone. */
  win.addEventListener("keydown", function (e) {
    if (!e || e.key !== "Escape") return;
    var asked = false;
    pending.forEach(function (p) {
      if (p.method !== "page.pick" || p.cancelled) return;
      p.cancelled = true;
      asked = true;
    });
    if (asked) request("page.cancelPick", []).catch(function () {});
  });

  win.deai = {
    ready: ready,
    hello: function () { return request("hello", []); },
    context: function () { return request("context", []); },
    selection: function () { return request("selection", []); },
    call: function (fn, args) { return request("call", [fn, args]); },
    page: {
      info: function () { return request("page.info", []); },
      query: function (selector, opts) { return request("page.query", [selector, opts]); },
      get: function (ref, opts) { return request("page.get", [ref, opts]); },
      snapshot: function (opts) { return request("page.snapshot", [opts]); },
      pick: function () { return request("page.pick", [], 0); },
      reveal: function (ref) { return request("page.reveal", [ref]); },
      cancelPick: function () { return request("page.cancelPick", []); },
      mark: function (ref, opts) { return request("page.mark", [ref, opts]); },
      unmark: function (id) { return request("page.unmark", [id]); },
      clearMarks: function () { return request("page.clearMarks", []); },
      setStyle: function (ref, map) { return request("page.setStyle", [ref, map]); },
      setClass: function (ref, ch) { return request("page.setClass", [ref, ch]); },
      setAttr: function (ref, name, value) { return request("page.setAttr", [ref, name, value]); },
      setText: function (ref, text) { return request("page.setText", [ref, text]); },
      revert: function (id) { return request("page.revert", [id]); },
      revertAll: function () { return request("page.revertAll", []); },
      listen: function (opts) { return request("page.listen", [opts]); }
    },
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
