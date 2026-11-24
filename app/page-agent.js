/**
 * Помічник ядра для модулів (М2): працює над документом рамки макета ЗІ СВОГО вікна (те саме походження) — як
 * інспектор і тюнер. Код модуля сюди не потрапляє: модуль лише просить через міст (`module-host.js`).
 * ⛔ Жоден рядок від модуля не йде в `innerHTML`/`insertAdjacentHTML`/`eval` чи атрибут поза `attrAllowed` —
 * лише `textContent`, `style.setProperty`, `classList`. Стереже статичний тест у `tests/page-rules.test.mjs`.
 * ⛔ Вузли — з ІНШОГО вікна: жодного `instanceof`, лише `nodeType`/`localName`.
 */
import { LIMITS, PageError, TONE_COLORS, checkLabel, checkStyleNames, checkTone, isCoreAttr } from "./page-rules.js";

const OURS = "[data-canvas-inspector],[data-comment-layer],#cl-down,[data-deai-marks]";
const SKIP = new Set(["script", "style", "template", "noscript"]);
const clip = (s, n) => (s.length > n ? s.slice(0, n) : s);
const round = (x) => Math.round(x * 10) / 10;
const utf8 = new TextEncoder();
const bytesOf = (v) => utf8.encode(JSON.stringify(v)).length;
const SELECTOR_MAX = 300, PSEUDO_MAX = 4, REFS_SWEEP = 20000;
/** Випадкова «епоха» помічника: посилання `r<епоха>-<n>` з попереднього екземпляра не збігається з новими. */
function newEpoch() {
  const u = new Uint32Array(2);
  (globalThis.crypto?.getRandomValues ? globalThis.crypto.getRandomValues(u) : u.forEach((_, i) => { u[i] = Math.random() * 2 ** 32; }));
  return (u[0].toString(36) + u[1].toString(36)).slice(0, 6);
}

export function createPageAgent({ doc, onEvent = () => {}, pageInfo = () => null }) {
  const win = doc.defaultView;
  let alive = true;
  let seq = 0;
  let sweepAt = REFS_SWEEP;
  const epoch = newEpoch();
  const byEl = new WeakMap();
  const byRef = new Map();

  const live = () => { if (!alive || !doc.defaultView) throw new PageError("no-page", "no live mockup page"); };
  const isOurs = (el) => !!el.closest(OURS);
  const inBody = (el) => !!doc.body && doc.body.contains(el) && !el.closest("script,style,template,noscript");
  function refOf(el) {
    let r = byEl.get(el);
    if (!r) {
      r = `r${epoch}-${++seq}`; byEl.set(el, r); byRef.set(r, new WeakRef(el));
      if (byRef.size > sweepAt) sweepRefs();
    }
    return r;
  }
  /** Мапа посилань росте лише з новими вузлами: вичищаємо зниклі й відчеплені; якщо живих усе одно багато — не чистимо щоразу. */
  function sweepRefs() {
    for (const [k, w] of byRef) { const e = w.deref(); if (!e || !e.isConnected) byRef.delete(k); }
    sweepAt = Math.max(REFS_SWEEP, byRef.size + 5000);
  }
  function elOf(ref) {
    live();
    const el = typeof ref === "string" ? byRef.get(ref)?.deref() : null;
    if (!el || !el.isConnected || el.ownerDocument !== doc || !inBody(el) || isOurs(el)) throw new PageError("stale-ref", "the element is gone or the page reloaded");
    return el;
  }
  function ownText(el) {
    let s = "";
    for (const n of el.childNodes) if (n.nodeType === 3) s += n.nodeValue;
    return clip(s.replace(/\s+/g, " ").trim(), LIMITS.nodeText);
  }
  function attrsOf(el) {
    const out = Object.create(null);
    let k = 0;
    for (const a of el.attributes) {
      if (isCoreAttr(a.name)) continue;
      if (k++ >= LIMITS.attrs) break;
      out[a.name] = clip(a.value, LIMITS.attrVal);
    }
    return out;
  }
  function describe(el, o = {}) {
    const r = el.getBoundingClientRect();
    const cs = win.getComputedStyle(el);
    const cls = el.getAttribute("class") || "";
    const n = { ref: refOf(el), tag: el.localName, id: el.id || "", cls: clip(cls, LIMITS.cls), text: ownText(el),
      rect: { x: round(r.left + win.scrollX), y: round(r.top + win.scrollY), w: round(r.width), h: round(r.height) },
      visible: r.width > 0 && r.height > 0 && cs.visibility !== "hidden" && cs.display !== "none" };
    if (o.attrs === true) n.attrs = attrsOf(el);
    if (o.styles && o.styles.length) { n.styles = {}; for (const p of o.styles) n.styles[p] = clip(cs.getPropertyValue(p), LIMITS.styleVal); }
    return n;
  }
  const opts = (o) => ({ styles: checkStyleNames(o?.styles), attrs: o?.attrs === true });
  function intIn(v, dflt, max, name) {
    if (v === undefined) return dflt;
    if (!Number.isInteger(v) || v < 1) throw new PageError("bad-args", `${name}: a positive integer`);
    return Math.min(v, max);
  }

  // ---------- мітки, показ, вибір: усе в тіньовому корені одного хоста; без innerHTML ----------
  const STYLE = `:host{all:initial}
.w[hidden]{display:none}
.mk{position:fixed;box-sizing:border-box;border:2px solid var(--t);background:color-mix(in srgb,var(--t) 9%,transparent);border-radius:4px;pointer-events:none}
.mk[hidden]{display:none}
.mk.fl{animation:fl .6s 2}
@keyframes fl{50%{box-shadow:0 0 0 7px color-mix(in srgb,var(--t) 45%,transparent)}}
@media (prefers-reduced-motion:reduce){.mk.fl{animation:none;box-shadow:0 0 0 4px color-mix(in srgb,var(--t) 45%,transparent)}}
.l{position:absolute;left:-2px;bottom:100%;margin-bottom:3px;max-width:240px;padding:2px 6px;border-radius:4px;background:var(--t);color:#151d19;font:600 11px/16px system-ui,-apple-system,"Segoe UI",sans-serif;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.l.dn{bottom:auto;top:100%;margin:3px 0 0}
.l:empty{display:none}
.cv{position:fixed;inset:0;cursor:crosshair;pointer-events:auto;background:transparent}
.pk{position:fixed;box-sizing:border-box;border:2px solid #3D8BFF;background:rgba(61,139,255,.1);border-radius:3px;pointer-events:none}
.pk[hidden]{display:none}
.pk span{position:absolute;left:-2px;top:100%;margin-top:3px;padding:2px 6px;border-radius:4px;background:#3D8BFF;color:#fff;font:600 11px/16px ui-monospace,SFMono-Regular,Menlo,monospace;white-space:nowrap}`;
  const PAD = 3, FLASH_MS = 1200, FLIP_TOP = 22;
  let host = null, root = null, wrap = null;
  function ensureHost() {
    if (host && host.isConnected) return;
    host = doc.createElement("div");
    host.setAttribute("data-deai-marks", "");
    host.setAttribute("data-h2d-ignore", "true");         // «В Figma» пропускає лише зі значенням "true"
    host.style.setProperty("all", "initial", "important");
    for (const [k, v] of [["position", "fixed"], ["top", "0"], ["left", "0"], ["width", "0"], ["height", "0"],
      ["z-index", "2147482999"], ["pointer-events", "none"]]) host.style.setProperty(k, v, "important");
    doc.documentElement.appendChild(host);                  // не в body: не стаємо учасником розкладки сторінки
    root = host.attachShadow({ mode: "open" });             // open: так само, як у оверлея інспектора; тести читають корінь
    const st = doc.createElement("style"); st.textContent = STYLE; root.appendChild(st);
    wrap = doc.createElement("div"); wrap.className = "w"; root.appendChild(wrap);
    marks.clear();                                          // хост пересотворено (сторінку перемалювали) — старі коробки зникли
  }

  const marks = new Map();                                  // id → {el: WeakRef, box, lab, timer}
  let markSeq = 0, tempSeq = 0, raf = 0, observer = null, listening = false;
  const permanent = () => { let n = 0; for (const m of marks.values()) if (!m.temp) n++; return n; };
  function place() {
    raf = 0;
    for (const m of marks.values()) {
      const el = m.el.deref();
      if (!el || !el.isConnected) { m.box.hidden = true; continue; }
      const r = el.getBoundingClientRect();
      m.box.hidden = false;
      m.box.style.setProperty("left", `${r.left - PAD}px`);
      m.box.style.setProperty("top", `${r.top - PAD}px`);
      m.box.style.setProperty("width", `${r.width + 2 * PAD}px`);
      m.box.style.setProperty("height", `${r.height + 2 * PAD}px`);
      m.lab.classList.toggle("dn", r.top < FLIP_TOP);
    }
  }
  function schedule() { if (!raf && alive) raf = win.requestAnimationFrame(place); }
  function attach() {
    if (listening) return;
    listening = true;
    doc.addEventListener("scroll", schedule, { capture: true, passive: true });
    win.addEventListener("resize", schedule);
    observer = new win.MutationObserver(schedule);
    observer.observe(doc.documentElement, { subtree: true, childList: true, attributes: true, characterData: true });
  }
  function detach() {
    if (!listening) return;
    listening = false;
    doc.removeEventListener("scroll", schedule, { capture: true });
    win.removeEventListener("resize", schedule);
    observer?.disconnect(); observer = null;
    if (raf) { win.cancelAnimationFrame(raf); raf = 0; }
  }
  function addMark(el, tone, label, temp) {
    ensureHost();
    const box = doc.createElement("div"); box.className = "mk"; box.hidden = true;
    box.style.setProperty("--t", TONE_COLORS[tone]);
    const lab = doc.createElement("div"); lab.className = "l"; lab.textContent = label;
    box.appendChild(lab); wrap.appendChild(box);
    const id = temp ? `t${++tempSeq}` : `m${++markSeq}`;
    marks.set(id, { el: new WeakRef(el), box, lab, timer: 0, temp });
    attach(); place();
    return id;
  }
  function dropMark(id) {
    const m = marks.get(id);
    if (!m) return;
    if (m.timer) win.clearTimeout(m.timer);
    m.box.remove(); marks.delete(id);
    if (!marks.size) detach();
  }

  // ---------- вибір елемента ----------
  let pickState = null;
  function finishPick(value) {
    const st = pickState;
    if (!st) return;
    pickState = null;
    doc.removeEventListener("keydown", st.onKey, true);
    st.cv.remove(); st.pk.remove();
    if (wrap) wrap.hidden = false;
    st.resolve(value);
  }
  function topAt(x, y) {
    for (const el of doc.elementsFromPoint(x, y)) {
      if (el === host || el === doc.documentElement || isOurs(el) || !inBody(el)) continue;
      return el;
    }
    return null;
  }
  function startPick() {
    live();
    finishPick(null);
    ensureHost();
    return new Promise((resolve) => {
      wrap.hidden = true;                                   // мітки не заважають вибору
      const cv = doc.createElement("div"); cv.className = "cv";
      const pk = doc.createElement("div"); pk.className = "pk"; pk.hidden = true;
      const cap = doc.createElement("span"); pk.appendChild(cap);
      root.appendChild(cv); root.appendChild(pk);
      let cur = null;
      cv.addEventListener("mousemove", (ev) => {
        cur = topAt(ev.clientX, ev.clientY);
        if (!cur) { pk.hidden = true; return; }
        const r = cur.getBoundingClientRect();
        pk.hidden = false;
        pk.style.setProperty("left", `${r.left}px`); pk.style.setProperty("top", `${r.top}px`);
        pk.style.setProperty("width", `${r.width}px`); pk.style.setProperty("height", `${r.height}px`);
        const c = (cur.getAttribute("class") || "").split(/\s+/)[0];
        cap.textContent = `${cur.localName}${c ? "." + c : ""} ${Math.round(r.width)}×${Math.round(r.height)}`;
      });
      cv.addEventListener("click", (ev) => {
        if (ev.button !== 0) return;
        ev.preventDefault(); ev.stopPropagation();
        const el = topAt(ev.clientX, ev.clientY);
        finishPick(el ? describe(el) : null);
      });
      // сторінка не бачить жестів, якими користувач цілиться (клік сюди — вибір, а не дія на сторінці)
      for (const t of ["mousedown", "mouseup", "pointerdown", "pointerup", "dblclick", "auxclick", "contextmenu"])
        cv.addEventListener(t, (ev) => { ev.preventDefault(); ev.stopPropagation(); });
      const onKey = (ev) => { if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); finishPick(null); } };
      doc.addEventListener("keydown", onKey, true);
      pickState = { resolve, cv, pk, onKey };
    });
  }

  const api = {
    get alive() { return alive; },
    info() {
      live();
      const de = doc.documentElement;
      return { page: pageInfo(), viewport: { w: win.innerWidth, h: win.innerHeight },
        scroll: { x: round(win.scrollX), y: round(win.scrollY) }, size: { w: de.scrollWidth, h: de.scrollHeight } };
    },
    query(selector, o = {}) {
      live();
      if (typeof selector !== "string" || !selector || selector.length > SELECTOR_MAX) throw new PageError("bad-args", `selector: a non-empty string of at most ${SELECTOR_MAX} characters`);
      if ((selector.match(/:(has|is|not|where)\(/gi) || []).length > PSEUDO_MAX) throw new PageError("bad-args", `selector: at most ${PSEUDO_MAX} functional pseudo-classes`);
      const limit = intIn(o?.limit, LIMITS.queryDefault, LIMITS.queryMax, "limit");
      const so = opts(o);
      let found;
      try { found = doc.querySelectorAll(selector); } catch (e) { throw new PageError("bad-selector", String(e?.message || e).slice(0, 200)); }
      const out = [];
      let bytes = 0;
      for (const el of found) {
        if (out.length >= limit) break;
        if (!inBody(el) || isOurs(el)) continue;
        const n = describe(el, so);
        bytes += bytesOf(n);
        if (bytes > LIMITS.snapshotBytes) break;
        out.push(n);
      }
      return out;
    },
    get(ref, o = {}) { return describe(elOf(ref), opts(o)); },
    snapshot(o = {}) {
      live();
      const max = intIn(o?.maxNodes, LIMITS.snapshotDefault, LIMITS.snapshotMax, "maxNodes");
      const so = opts(o);
      const nodes = [];
      let bytes = 0, truncated = false;
      if (doc.body) {
        const walker = doc.createTreeWalker(doc.body, 1, { acceptNode: (n) => (SKIP.has(n.localName) || n.matches(OURS) ? 2 : 1) });
        for (let el = walker.currentNode; el; el = walker.nextNode()) {
          if (nodes.length >= max) { truncated = true; break; }
          const n = describe(el, so);
          n.parent = el === doc.body ? null : refOf(el.parentElement);
          bytes += bytesOf(n);
          if (bytes > LIMITS.snapshotBytes) { truncated = true; break; }
          nodes.push(n);
        }
      }
      return { info: api.info(), truncated, nodes };
    },
    mark(ref, o) {
      const el = elOf(ref);
      const tone = checkTone(o?.tone), label = checkLabel(o?.label);
      if (permanent() >= LIMITS.marks) throw new PageError("too-many", `at most ${LIMITS.marks} marks`);
      return addMark(el, tone, label, false);
    },
    unmark(id) { live(); if (typeof id === "string") dropMark(id); return null; },
    clearMarks() { live(); for (const id of [...marks.keys()]) dropMark(id); return null; },
    reveal(ref) {
      const el = elOf(ref);
      const reduced = win.matchMedia("(prefers-reduced-motion: reduce)").matches;
      let own = null;
      for (const [id, m] of marks) if (!m.temp && m.el.deref() === el) { own = id; break; }
      let id = own;
      if (!id) id = addMark(el, "info", "", true);          // без мітки — тимчасова рамка
      el.scrollIntoView({ block: "center", inline: "nearest", behavior: reduced ? "auto" : "smooth" });
      const m = marks.get(id);
      if (own) { m.box.classList.remove("fl"); void m.box.offsetWidth; m.box.classList.add("fl"); }
      if (m.timer) win.clearTimeout(m.timer);
      m.timer = win.setTimeout(() => { m.timer = 0; if (own) m.box.classList.remove("fl"); else dropMark(id); }, FLASH_MS);
      return null;
    },
    pick() { return startPick(); },
    cancelPick() { finishPick(null); },
    get picking() { return !!pickState; },
    destroy() {
      if (!alive) return;
      finishPick(null);
      for (const id of [...marks.keys()]) dropMark(id);
      detach();
      host?.remove(); host = root = wrap = null;
      alive = false;
      byRef.clear();
    },
  };
  return api;
}
