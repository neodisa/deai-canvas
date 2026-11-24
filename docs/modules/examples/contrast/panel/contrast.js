// Tool panel «Contrast»: checks the mockup page through the core helper `deai.page.*`. No network, no frameworks.
// The pure logic lives in `Contrast` (testable in Node); the UI flow starts only when `window.deai` exists.
var Contrast = (function () {
  "use strict";
  var STYLES = ["color", "background-color", "font-size", "font-weight"];
  var TEXT = {
    uk: { pick: "Вибрати елемент", show: "Показати", fix: "Спробувати виправлення", fixed: "тимчасово виправлено",
      temp: "Тимчасових змін: ", cancel: "Скасувати", none: "Проблем не знайдено", noneHere: "Цей елемент без знахідок",
      contrast: "Контраст", noLabel: "Немає підпису поля", noAlt: "Немає опису зображення", noPage: "Без сторінки" },
    en: { pick: "Pick element", show: "Show", fix: "Try a fix", fixed: "fixed temporarily",
      temp: "Temporary changes: ", cancel: "Revert", none: "No problems found", noneHere: "No findings for this element",
      contrast: "Contrast", noLabel: "Field has no label", noAlt: "Image has no description", noPage: "No page" }
  };
  var lang = "uk";
  function t(key) { return TEXT[lang][key]; }
  function setLang(l) { lang = l === "en" ? "en" : "uk"; }
  function getLang() { return lang; }
  function has(o, k) { return !!o && Object.prototype.hasOwnProperty.call(o, k); }
  // A value counts as a name only when it is a string with something besides whitespace.
  function filled(o, k) { return has(o, k) && typeof o[k] === "string" && o[k].trim() !== ""; }

  function num(v) { return /%$/.test(v) ? parseFloat(v) / 100 : parseFloat(v); }
  // "rgb(1, 2, 3)", "rgba(1, 2, 3, 0.5)", "rgb(1 2 3 / 50%)", "color(srgb 0.1 0.2 0.3 / 0.5)", "transparent" -> {r, g, b, a} (0..255) or null.
  // Any other colour space (oklch, lab, display-p3, srgb-linear…) gives null: converting it to sRGB here would be a guess,
  // and a wrong guess makes a false finding, so such a node is skipped instead.
  function parseColor(s) {
    s = String(s || "").trim();
    if (/^transparent$/i.test(s)) return { r: 0, g: 0, b: 0, a: 0 };
    var m = /^rgba?\(\s*([\d.]+)[ ,]+([\d.]+)[ ,]+([\d.]+)(?:\s*[,/]\s*([\d.]+%?))?\s*\)$/i.exec(s);
    if (m) return { r: +m[1], g: +m[2], b: +m[3], a: m[4] !== undefined ? num(m[4]) : 1 };
    m = /^color\(\s*srgb\s+([\d.]+%?)\s+([\d.]+%?)\s+([\d.]+%?)(?:\s*\/\s*([\d.]+%?))?\s*\)$/i.exec(s);
    if (m) return { r: num(m[1]) * 255, g: num(m[2]) * 255, b: num(m[3]) * 255, a: m[4] !== undefined ? num(m[4]) : 1 };
    return null;
  }
  function luminance(c) {
    function ch(v) { v = v / 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }
    return 0.2126 * ch(c.r) + 0.7152 * ch(c.g) + 0.0722 * ch(c.b);
  }
  function ratio(a, b) {
    var la = luminance(a), lb = luminance(b);
    var hi = Math.max(la, lb), lo = Math.min(la, lb);
    return (hi + 0.05) / (lo + 0.05);
  }
  // The ratio as shown to people: floored to one decimal, so a failing 4.46 never reads «4.5:1».
  function shown(r) { return (Math.floor(r * 10 + 1e-9) / 10).toFixed(1); }
  // WCAG «large text»: at least 24 px, or at least 18.66 px (14 pt) and bold.
  function isLarge(fontSizePx, weight) {
    var size = parseFloat(fontSizePx), w = parseInt(weight, 10) || 400;
    return size >= 24 || (size >= 18.66 && w >= 700);
  }
  var WHITE = { r: 255, g: 255, b: 255, a: 1 }, BLACK = { r: 0, g: 0, b: 0, a: 1 };
  // `top` drawn over the opaque `base`.
  function over(top, base) {
    var a = top.a;
    return { r: top.r * a + base.r * (1 - a), g: top.g * a + base.g * (1 - a), b: top.b * a + base.b * (1 - a), a: 1 };
  }
  // The background under a node: its own and its ancestors' semi-transparent layers composited up to the first opaque
  // one (white above the top, or where the `parent` chain is cut). null when a layer is in a colour space we skip.
  function bgOf(node, byRef) {
    var layers = [], base = WHITE;
    for (var n = node, guard = 0; n && guard < 1000; guard++) {
      var raw = n.styles && n.styles["background-color"];
      if (raw !== undefined && raw !== null && String(raw).trim() !== "") {
        var c = parseColor(raw);
        if (!c) return null;
        if (c.a >= 0.99) { base = c; break; }
        if (c.a > 0) layers.push(c);
      }
      n = n.parent ? byRef[n.parent] : null;
    }
    for (var i = layers.length - 1; i >= 0; i--) base = over(layers[i], base);
    return base;
  }
  function rgbString(c) { return "rgb(" + Math.round(c.r) + ", " + Math.round(c.g) + ", " + Math.round(c.b) + ")"; }

  var SKIP_INPUT = { hidden: 1, submit: 1, button: 1, reset: 1, image: 1 };
  // Findings of a snapshot: [{ref, tag, text, tone, label, fix?: {color}}].
  function findings(snap) {
    var nodes = snap.nodes || [], byRef = Object.create(null), labelFor = Object.create(null), out = [];
    nodes.forEach(function (n) {
      byRef[n.ref] = n;
      if (n.tag === "label" && filled(n.attrs, "for")) labelFor[n.attrs["for"]] = true;
    });
    // An input inside a <label> is labelled by it (walk the `parent` refs; a cut chain just ends the walk).
    function inLabel(n) {
      for (var p = n.parent ? byRef[n.parent] : null, guard = 0; p && guard < 1000; guard++) {
        if (p.tag === "label") return true;
        p = p.parent ? byRef[p.parent] : null;
      }
      return false;
    }
    nodes.forEach(function (n) {
      var attrs = n.attrs || {};
      if (n.text && n.visible && n.styles) {
        var fg = parseColor(n.styles.color), bg = fg ? bgOf(n, byRef) : null;
        if (fg && bg) {
          var text = over(fg, bg), r = ratio(text, bg);        // semi-transparent text is mixed with its background
          var need = isLarge(n.styles["font-size"], n.styles["font-weight"]) ? 3 : 4.5;
          if (r < need) {
            var best = ratio(BLACK, bg) >= ratio(WHITE, bg) ? BLACK : WHITE;
            out.push({ ref: n.ref, tag: n.tag, text: n.text, tone: r < 3 ? "error" : "warn",
              label: t("contrast") + " " + shown(r) + ":1", fix: { color: rgbString(best) } });
          }
        }
      }
      if ((n.tag === "input" || n.tag === "select" || n.tag === "textarea") && n.visible && !SKIP_INPUT[String(attrs.type || "").toLowerCase()]) {
        var named = filled(attrs, "aria-label") || filled(attrs, "aria-labelledby") || filled(attrs, "title") ||
          (n.id && labelFor[n.id]) || inLabel(n);
        if (!named) out.push({ ref: n.ref, tag: n.tag, text: "<" + n.tag + (n.id ? "#" + n.id : "") + ">", tone: "warn", label: t("noLabel") });
      }
      if ((n.tag === "img" && !has(attrs, "alt")) || (attrs.role === "img" && !filled(attrs, "aria-label") && !filled(attrs, "aria-labelledby"))) {
        out.push({ ref: n.ref, tag: n.tag, text: "<" + n.tag + (n.id ? "#" + n.id : "") + ">", tone: "info", label: t("noAlt") });
      }
    });
    return out;
  }

  return { STYLES: STYLES, parseColor: parseColor, parseRgb: parseColor, luminance: luminance, ratio: ratio, isLarge: isLarge,
    bgOf: bgOf, findings: findings, t: t, setLang: setLang, getLang: getLang };
})();

(function () {
  "use strict";
  if (typeof window === "undefined" || !window.deai) return;
  var deai = window.deai, C = Contrast;
  var $ = function (id) { return document.getElementById(id); };
  var items = [], parents = {}, changes = [], pageTitle = "";
  var loaded = false;            // false until the first `page` event: the body stays empty, no «0 findings» for a page we have not seen
  var seq = 0;                   // number of the newest run; results of an older run are dropped
  var running = false, picking = false;

  function fail(action, e) { deai.toast(action + ": " + (e && e.code ? e.code : String((e && e.message) || e))); }
  function plural(n) {
    if (C.getLang() === "en") return n + " " + (n === 1 ? "finding" : "findings");
    var m10 = n % 10, m100 = n % 100;
    return n + " " + (m10 === 1 && m100 !== 11 ? "знахідка" : (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14) ? "знахідки" : "знахідок"));
  }
  function btn(text, onclick) {
    var b = document.createElement("button");
    b.type = "button"; b.className = "dk-btn dk-btn--sm"; b.textContent = text; b.onclick = onclick;
    return b;
  }

  function render() {
    $("pick").textContent = C.t("pick");
    $("revert").textContent = C.t("cancel");
    var list = $("list");
    list.textContent = "";
    if (!loaded) { $("sum").textContent = ""; $("tmp").hidden = true; return; }
    $("sum").textContent = (pageTitle || C.t("noPage")) + " · " + plural(items.length);
    if (!items.length) {
      var li = document.createElement("li");
      li.className = "dk-empty"; li.textContent = C.t("none");
      list.appendChild(li);
    }
    items.forEach(function (f, i) {
      var row = document.createElement("li");
      row.className = "dk-row tone-" + (f.done ? "ok" : f.tone);
      row.id = "row-" + i;
      var dot = document.createElement("span"); dot.className = "dot";
      var t = document.createElement("div"); t.className = "row-t";
      var main = document.createElement("div"); main.textContent = f.text;
      var small = document.createElement("small"); small.textContent = f.done ? C.t("fixed") : f.label;
      t.appendChild(main); t.appendChild(small);
      var acts = document.createElement("div"); acts.className = "row-acts";
      acts.appendChild(btn(C.t("show"), function () { deai.page.reveal(f.ref).catch(function (e) { fail("reveal", e); }); }));
      if (f.fix && !f.done) acts.appendChild(btn(C.t("fix"), function () { tryFix(f); }));
      row.appendChild(dot); row.appendChild(t); row.appendChild(acts);
      list.appendChild(row);
    });
    $("tmp").hidden = !changes.length;
    $("tmp-t").textContent = C.t("temp") + changes.length;
  }

  // Highlights and scrolls the row of finding `i`; false when there is no such row.
  function hot(i) {
    var row = $("row-" + i);
    if (!row) return false;
    Array.prototype.forEach.call(document.querySelectorAll(".dk-row.hot"), function (r) { r.classList.remove("hot"); });
    row.classList.add("hot");
    row.scrollIntoView({ block: "nearest" });
    return true;
  }
  function indexOfRef(ref) { return items.findIndex(function (f) { return f.ref === ref; }); }

  async function tryFix(f) {
    if (f.busy || f.done) return;                 // a double click must not apply (and count) the fix twice
    f.busy = true;
    var my = seq;
    try {
      var r;
      try { r = await deai.page.setStyle(f.ref, { color: f.fix.color }); }
      catch (e) { if (my === seq) fail("setStyle", e); return; }
      if (my !== seq) return;                     // a newer run started: this item and the counter are not ours any more
      if (r.id) changes.push(r.id);
      f.done = true;
      try {
        if (f.mark) await deai.page.unmark(f.mark);
        f.mark = await deai.page.mark(f.ref, { tone: "ok", label: C.t("fixed") });
      } catch (e) { if (my === seq) fail("mark", e); }
      if (my !== seq) { if (f.mark) deai.page.unmark(f.mark).catch(function () {}); return; }
      render();
    } finally { f.busy = false; }
  }

  async function runOnce(my) {
    var stale = function () { return my !== seq; };
    var toasted = false;
    function failOnce(action, e) { if (stale() || toasted) return; toasted = true; fail(action, e); }
    changes = [];                                 // a new page or a revert: the core dropped the old changes and marks
    try { await deai.page.clearMarks(); } catch (e) { failOnce("clearMarks", e); }
    if (stale()) return;
    var snap;
    try { snap = await deai.page.snapshot({ styles: C.STYLES, attrs: true }); }
    catch (e) { failOnce("snapshot", e); if (!stale()) { items = []; parents = {}; render(); } return; }
    if (stale()) return;
    pageTitle = snap.info && snap.info.page ? snap.info.page.title : "";
    parents = {};
    (snap.nodes || []).forEach(function (n) { if (n.parent) parents[n.ref] = n.parent; });
    items = C.findings(snap);
    for (var i = 0; i < items.length; i++) {
      try { items[i].mark = await deai.page.mark(items[i].ref, { tone: items[i].tone, label: items[i].label }); }
      catch (e) { failOnce("mark", e); break; }
      if (stale()) return;
    }
    render();
  }

  // One run at a time (two at once would interleave their marks and clears); a request made meanwhile reruns afterwards.
  async function run() {
    seq++;
    if (running) return;
    running = true;
    try {
      var my;
      do { my = seq; await runOnce(my); } while (my !== seq);
    } finally { running = false; }
  }

  async function pickOne() {
    if (picking) { deai.page.cancelPick().catch(function (e) { fail("cancelPick", e); }); return; }
    picking = true;
    $("pick").setAttribute("aria-pressed", "true");
    var node;
    try { node = await deai.page.pick(); }
    catch (e) { fail("pick", e); return; }
    finally { picking = false; $("pick").setAttribute("aria-pressed", "false"); }
    if (!node) return;
    var i = indexOfRef(node.ref);
    if (i < 0) { deai.toast(C.t("noneHere")); return; }
    if (!hot(i)) return;
    deai.page.reveal(node.ref).catch(function (e) { fail("reveal", e); });
  }

  // A click in the mockup: the row of the clicked element, or of its nearest ancestor that has a finding.
  function onClick(d) {
    var node = d && d.node;
    if (!node) return;
    for (var ref = node.ref, guard = 0; ref && guard < 1000; guard++) {
      var i = indexOfRef(ref);
      if (i >= 0) { hot(i); return; }
      ref = parents[ref];
    }
  }

  $("pick").addEventListener("click", pickOne);
  $("revert").addEventListener("click", async function () {
    try { await deai.page.revertAll(); } catch (e) { fail("revertAll", e); }
    run();
  });
  deai.on("page", function () {                   // the core sends `page` after `init` and after every page load
    loaded = true;
    deai.page.listen({ click: true }).catch(function () {});   // listeners end with the page: ask again after every `page`; the run reports page problems
    run();
  });
  deai.on("page-click", onClick);
  deai.ready.then(function (init) {
    C.setLang(init && init.context ? init.context.lang : "uk");
    render();
  });
})();
