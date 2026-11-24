// Tool panel «Contrast»: checks the mockup page through the core helper `deai.page.*`. No network, no frameworks.
// The pure logic lives in `Contrast` (testable in Node); the UI flow starts only when `window.deai` exists.
var Contrast = (function () {
  "use strict";
  var STYLES = ["color", "background-color", "font-size", "font-weight"];
  var TEXT = {
    uk: { found: "знахідок", pick: "Вибрати елемент", show: "Показати", fix: "Спробувати виправлення",
      fixed: "тимчасово виправлено", temp: "Тимчасових змін: ", cancel: "Скасувати", none: "Проблем не знайдено",
      contrast: "Контраст", noLabel: "Немає підпису поля", noAlt: "Немає опису зображення", noPage: "Без сторінки",
      image: "Зображення" },
    en: { found: "findings", pick: "Pick element", show: "Show", fix: "Try a fix", fixed: "fixed temporarily",
      temp: "Temporary changes: ", cancel: "Revert", none: "No problems found", contrast: "Contrast",
      noLabel: "Field has no label", noAlt: "Image has no description", noPage: "No page", image: "Image" }
  };
  var lang = "uk";
  function t(key) { return (TEXT[lang] || TEXT.uk)[key]; }
  function setLang(l) { lang = l === "en" ? "en" : "uk"; }
  function has(o, k) { return !!o && Object.prototype.hasOwnProperty.call(o, k); }

  // "rgb(1, 2, 3)" / "rgba(1, 2, 3, 0.5)" -> {r, g, b, a} or null.
  function parseRgb(s) {
    var m = /^rgba?\(\s*([\d.]+)[ ,]+([\d.]+)[ ,]+([\d.]+)(?:\s*[,/]\s*([\d.]+%?))?\s*\)$/i.exec(String(s || "").trim());
    if (!m) return null;
    var a = 1;
    if (m[4] !== undefined) a = /%$/.test(m[4]) ? parseFloat(m[4]) / 100 : parseFloat(m[4]);
    return { r: +m[1], g: +m[2], b: +m[3], a: a };
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
  // WCAG «large text»: at least 24 px, or at least 18.66 px (14 pt) and bold.
  function isLarge(fontSizePx, weight) {
    var size = parseFloat(fontSizePx), w = parseInt(weight, 10) || 400;
    return size >= 24 || (size >= 18.66 && w >= 700);
  }
  var WHITE = { r: 255, g: 255, b: 255, a: 1 }, BLACK = { r: 0, g: 0, b: 0, a: 1 };
  // The nearest ancestor (or the node itself) with an opaque background; white when there is none.
  function bgOf(node, byRef) {
    for (var n = node, guard = 0; n && guard < 1000; guard++) {
      var c = parseRgb(n.styles && n.styles["background-color"]);
      if (c && c.a >= 0.99) return c;
      n = n.parent ? byRef[n.parent] : null;
    }
    return WHITE;
  }
  function rgbString(c) { return "rgb(" + c.r + ", " + c.g + ", " + c.b + ")"; }

  var SKIP_INPUT = { hidden: 1, submit: 1, button: 1, reset: 1, image: 1 };
  // Findings of a snapshot: [{ref, tag, text, tone, label, fix?: {color}}].
  function findings(snap) {
    var nodes = snap.nodes || [], byRef = Object.create(null), labelFor = Object.create(null), out = [];
    nodes.forEach(function (n) {
      byRef[n.ref] = n;
      if (n.tag === "label" && n.attrs && n.attrs["for"]) labelFor[n.attrs["for"]] = true;
    });
    nodes.forEach(function (n) {
      var attrs = n.attrs || {};
      if (n.text && n.visible && n.styles) {
        var fg = parseRgb(n.styles.color);
        if (fg) {
          var bg = bgOf(n, byRef), r = ratio(fg, bg);
          var need = isLarge(n.styles["font-size"], n.styles["font-weight"]) ? 3 : 4.5;
          if (r < need) {
            var best = ratio(BLACK, bg) >= ratio(WHITE, bg) ? BLACK : WHITE;
            out.push({ ref: n.ref, tag: n.tag, text: n.text, tone: r < 3 ? "error" : "warn",
              label: t("contrast") + " " + r.toFixed(1) + ":1", fix: { color: rgbString(best) } });
          }
        }
      }
      if ((n.tag === "input" || n.tag === "select" || n.tag === "textarea") && n.visible && !SKIP_INPUT[String(attrs.type || "").toLowerCase()]) {
        var named = has(attrs, "aria-label") || has(attrs, "aria-labelledby") || has(attrs, "title") || (n.id && labelFor[n.id]);
        if (!named) out.push({ ref: n.ref, tag: n.tag, text: "<" + n.tag + (n.id ? "#" + n.id : "") + ">", tone: "warn", label: t("noLabel") });
      }
      if ((n.tag === "img" && !has(attrs, "alt")) || (attrs.role === "img" && !has(attrs, "aria-label"))) {
        out.push({ ref: n.ref, tag: n.tag, text: "<" + n.tag + (n.id ? "#" + n.id : "") + ">", tone: "info", label: t("noAlt") });
      }
    });
    return out;
  }

  return { STYLES: STYLES, parseRgb: parseRgb, luminance: luminance, ratio: ratio, isLarge: isLarge, bgOf: bgOf,
    findings: findings, t: t, setLang: setLang };
})();

(function () {
  "use strict";
  if (typeof window === "undefined" || !window.deai) return;
  var deai = window.deai, C = Contrast;
  var $ = function (id) { return document.getElementById(id); };
  var items = [], changes = [], pageTitle = "", running = false, again = false;

  function fail(action, e) { deai.toast(action + ": " + (e && e.code ? e.code : String((e && e.message) || e))); }
  function plural(n) {
    if (C.t("found") === "findings") return n + " " + (n === 1 ? "finding" : "findings");
    var m10 = n % 10, m100 = n % 100;
    return n + " " + (m10 === 1 && m100 !== 11 ? "знахідка" : (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14) ? "знахідки" : "знахідок"));
  }
  function btn(text, onclick) {
    var b = document.createElement("button");
    b.type = "button"; b.className = "dk-btn dk-btn--sm"; b.textContent = text; b.onclick = onclick;
    return b;
  }

  function render() {
    $("sum").textContent = (pageTitle || C.t("noPage")) + " · " + plural(items.length);
    $("pick").textContent = C.t("pick");
    $("revert").textContent = C.t("cancel");
    var list = $("list");
    list.textContent = "";
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

  async function tryFix(f) {
    try {
      var r = await deai.page.setStyle(f.ref, { color: f.fix.color });
      if (r.id) changes.push(r.id);
    } catch (e) { fail("setStyle", e); return; }
    f.done = true;
    try {
      if (f.mark) await deai.page.unmark(f.mark);
      f.mark = await deai.page.mark(f.ref, { tone: "ok", label: C.t("fixed") });
    } catch (e) { fail("mark", e); }
    render();
  }

  async function snapshot() {
    return deai.page.snapshot({ styles: C.STYLES, attrs: true });
  }

  async function run() {
    if (running) { again = true; return; }        // `snapshot` answers `busy` to a second concurrent call
    running = true;
    try {
      do {
        again = false;
        changes = [];                             // a new page or a revert: the core dropped the old changes and marks
        try { await deai.page.clearMarks(); } catch (e) { fail("clearMarks", e); }
        var snap;
        try { snap = await snapshot(); } catch (e) { fail("snapshot", e); items = []; render(); continue; }
        pageTitle = snap.info && snap.info.page ? snap.info.page.title : "";
        items = C.findings(snap);
        for (var i = 0; i < items.length; i++) {
          try { items[i].mark = await deai.page.mark(items[i].ref, { tone: items[i].tone, label: items[i].label }); }
          catch (e) { fail("mark", e); break; }
        }
        render();
      } while (again);
    } finally { running = false; }
  }

  async function pickOne() {
    var node;
    try { node = await deai.page.pick(); } catch (e) { fail("pick", e); return; }
    if (!node) return;
    var i = items.findIndex(function (f) { return f.ref === node.ref; });
    if (i < 0) { deai.toast(C.t("none")); return; }
    var row = $("row-" + i);
    Array.prototype.forEach.call(document.querySelectorAll(".dk-row.hot"), function (r) { r.classList.remove("hot"); });
    row.classList.add("hot");
    row.scrollIntoView({ block: "nearest" });
    deai.page.reveal(node.ref).catch(function (e) { fail("reveal", e); });
  }

  $("pick").addEventListener("click", pickOne);
  $("revert").addEventListener("click", async function () {
    try { await deai.page.revertAll(); } catch (e) { fail("revertAll", e); }
    run();
  });
  deai.on("page", function () { run(); });         // the core sends `page` after `init` and after every page load
  deai.ready.then(function (init) {
    C.setLang(init && init.context ? init.context.lang : "uk");
    render();
  });
})();
