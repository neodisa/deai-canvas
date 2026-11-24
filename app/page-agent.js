/**
 * Помічник ядра для модулів (М2): працює над документом рамки макета ЗІ СВОГО вікна (те саме походження) — як
 * інспектор і тюнер. Код модуля сюди не потрапляє: модуль лише просить через міст (`module-host.js`).
 * ⛔ Жоден рядок від модуля не йде в `innerHTML`/`insertAdjacentHTML`/`eval` чи атрибут поза `attrAllowed` —
 * лише `textContent`, `style.setProperty`, `classList`. Стереже статичний тест у `tests/page-rules.test.mjs`.
 * ⛔ Вузли — з ІНШОГО вікна: жодного `instanceof`, лише `nodeType`/`localName`.
 */
import { LIMITS, PageError, TONE_COLORS, attrAllowed, checkAttrValue, checkClassList, checkLabel, checkStyleMap, checkStyleNames, checkText,
  checkTone, createJournal, isCoreAttr, stillOurs } from "./page-rules.js";

const OURS = "[data-canvas-inspector],[data-comment-layer],#cl-down,[data-deai-marks]";
const SKIP = new Set(["script", "style", "template", "noscript"]);
const clip = (s, n) => (s.length > n ? s.slice(0, n) : s);
const round = (x) => Math.round(x * 10) / 10;
const utf8 = new TextEncoder();
const bytesOf = (v) => utf8.encode(JSON.stringify(v)).length;
const SELECTOR_MAX = 300, PSEUDO_MAX = 4, PARENS_MAX = 8, REFS_SWEEP = 20000, TEMP_MAX = 20;
/** Випадкова «епоха» помічника: посилання `r<епоха>-<n>` з попереднього екземпляра не збігається з новими. */
function newEpoch() {
  const u = new Uint32Array(2);
  (globalThis.crypto?.getRandomValues ? globalThis.crypto.getRandomValues(u) : u.forEach((_, i) => { u[i] = Math.random() * 2 ** 32; }));
  return (u[0].toString(36) + u[1].toString(36)).slice(0, 6);
}

export function createPageAgent({ doc, onEvent = () => {}, pageInfo = () => null, _refsSweep = REFS_SWEEP }) {
  const win = doc.defaultView;
  let alive = true;
  let seq = 0;
  let sweepAt = _refsSweep;
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
  /** Мапа посилань росте лише з новими вузлами: вичищаємо лише ЗІБРАНІ збирачем (відчеплений, але живий вузол лишає посилання:
   *  `byEl` досі мапить його на старе, і після повернення в документ `refOf` має віддати те саме, що розуміє `elOf`).
   *  Якщо живих усе одно багато — не чистимо щоразу. */
  function sweepRefs() {
    for (const [k, w] of byRef) if (!w.deref()) byRef.delete(k);
    sweepAt = Math.max(_refsSweep, byRef.size + 5000);
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
.mk.fl{animation:fl .9s 2}
@keyframes fl{50%{box-shadow:0 0 0 7px color-mix(in srgb,var(--t) 45%,transparent)}}
@media (prefers-reduced-motion:reduce){.mk.fl{animation:none;box-shadow:0 0 0 4px color-mix(in srgb,var(--t) 45%,transparent)}}
.l{position:absolute;left:-2px;bottom:100%;margin-bottom:3px;max-width:240px;padding:2px 6px;border-radius:4px;background:var(--t);color:#151d19;font:600 11px/16px system-ui,-apple-system,"Segoe UI",sans-serif;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.l.dn{bottom:auto;top:100%;margin:3px 0 0}
.l:empty{display:none}
.cv{position:fixed;inset:0;cursor:crosshair;pointer-events:auto;background:transparent}
.pk{position:fixed;box-sizing:border-box;border:2px solid #3D8BFF;background:rgba(61,139,255,.1);border-radius:3px;pointer-events:none}
.pk[hidden]{display:none}
.pk span{position:absolute;left:-2px;top:100%;margin-top:3px;padding:2px 6px;border-radius:4px;background:#3D8BFF;color:#fff;font:600 11px/16px ui-monospace,SFMono-Regular,Menlo,monospace;white-space:nowrap}`;
  const PAD = 3, FLASH_MS = 1800, FLIP_TOP = 22;
  let host = null, root = null, wrap = null;
  /** Сторінка прибрала хост (замінила `documentElement.innerHTML` чи сам `documentElement`): коробки в мертвому корені не рахуються. */
  function resetHost() {
    for (const m of marks.values()) if (m.timer) win.clearTimeout(m.timer);
    marks.clear();
    host = root = wrap = null;
  }
  function ensureHost() {
    if (host && host.isConnected) return;
    resetHost();
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
    if (listening) { detach(); attach(); }                  // спостерігач міг дивитися на старий `documentElement`
  }

  const marks = new Map();                                  // id → {el: WeakRef, box, lab, timer}
  let markSeq = 0, tempSeq = 0, raf = 0, observer = null, listening = false;
  const permanent = () => { let n = 0; for (const m of marks.values()) if (!m.temp) n++; return n; };
  const tempCount = () => marks.size - permanent();
  function place() {
    raf = 0;
    if (host && !host.isConnected) {                        // хост прибрала сторінка
      finishPick(null);
      resetHost();
      if (!pickState && !marks.size) detach();
      return;
    }
    if (pickState && !pickState.cv.isConnected) finishPick(null);
    if (pickState) pickState.show();
    const rects = [];                                       // спершу читаємо всі прямокутники, потім пишемо стилі — без перерахунків
    for (const m of marks.values()) {
      const el = m.el.deref();
      rects.push(el && el.isConnected ? el.getBoundingClientRect() : null);
    }
    let i = 0;
    for (const m of marks.values()) {
      const r = rects[i++];
      if (!r || (r.width === 0 && r.height === 0)) { m.box.hidden = true; continue; }
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
    observer.observe(doc, { childList: true });             // замінили сам `documentElement` — старий спостерігач про це не знає
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
    if (!marks.size && !pickState) detach();
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
    if (!marks.size) detach();
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
      const show = () => {                                  // рамка й підпис поточної цілі; викликається і з прокрутки
        if (!cur || !cur.isConnected) { cur = null; pk.hidden = true; return; }
        const r = cur.getBoundingClientRect();
        pk.hidden = false;
        pk.style.setProperty("left", `${r.left}px`); pk.style.setProperty("top", `${r.top}px`);
        pk.style.setProperty("width", `${r.width}px`); pk.style.setProperty("height", `${r.height}px`);
        const c = (cur.getAttribute("class") || "").split(/\s+/)[0];
        cap.textContent = `${cur.localName}${c ? "." + c : ""} ${Math.round(r.width)}×${Math.round(r.height)}`;
      };
      cv.addEventListener("mousemove", (ev) => {
        cur = topAt(ev.clientX, ev.clientY);
        show();
        ev.stopPropagation();
      });
      cv.addEventListener("click", (ev) => {
        if (ev.button !== 0) return;
        ev.preventDefault(); ev.stopPropagation();
        const el = topAt(ev.clientX, ev.clientY);
        finishPick(el ? describe(el) : null);
      });
      // слухачі сторінки на бульбашковій фазі не бачать жестів, якими користувач цілиться (клік сюди — вибір, а не дія на
      // сторінці). Слухачі у фазі захоплення на window/document побачать їх першими — це не захист від ворожої сторінки.
      for (const t of ["mousedown", "mouseup", "pointerdown", "pointerup", "dblclick", "auxclick", "contextmenu"])
        cv.addEventListener(t, (ev) => { ev.preventDefault(); ev.stopPropagation(); });
      for (const t of ["pointermove", "mouseover", "mouseout", "pointerover", "pointerout", "touchstart", "touchmove", "touchend"])
        cv.addEventListener(t, (ev) => ev.stopPropagation(), { passive: true });   // `wheel` не чіпаємо: прокрутка має працювати
      const onKey = (ev) => { if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); finishPick(null); } };
      doc.addEventListener("keydown", onKey, true);
      pickState = { resolve, cv, pk, onKey, show };
      attach();                                             // спостерігач і прокрутка: рамка їде за ціллю, зниклий хост — вихід з null
    });
  }

  // ---------- зміни вигляду з журналом ----------
  // ⛔ Спершу `journal.full`, потім зміна документа: зміна без запису в журнал не відкотиться.
  const journal = createJournal();
  const notFull = () => { if (journal.full) throw new PageError("too-many", `at most ${LIMITS.changes} active changes`); };
  const styleNow = (el, p) => ({ v: el.style.getPropertyValue(p), pr: el.style.getPropertyPriority(p) });
  const sameStyle = (a, b) => stillOurs(a.v, b.v) && stillOurs(a.pr, b.pr);
  /** Порожній `style=""` після відкату прибираємо (як тюнер). Спершу читаємо атрибут: Chrome серіалізує `style` ліниво, і
   *  `removeAttribute` до цього лишає «брудний» стан, з якого `style=""` зʼявляється знову. */
  function dropEmptyStyle(el) {
    if (el.style.length !== 0) return;
    el.getAttribute("style");
    el.removeAttribute("style");
  }
  function putStyle(el, p, s) {
    el.style.removeProperty(p);
    if (s.v !== "") el.style.setProperty(p, s.v, s.pr);
  }
  /** Відкат одного запису → {reverted, skipped}; пункт рахується, лише якщо поточне досі «наше». */
  function revertEntry(e) {
    const el = e.el.deref();
    const n = e.kind === "style" ? e.items.length : e.kind === "class" ? e.added.length + e.removed.length : 1;
    if (!el || !el.isConnected) return { reverted: 0, skipped: n };
    let reverted = 0, skipped = 0;
    if (e.kind === "style") {
      for (let i = e.items.length - 1; i >= 0; i--) {
        const it = e.items[i];
        if (sameStyle(styleNow(el, it.p), it.after)) { putStyle(el, it.p, it.before); reverted++; } else skipped++;
      }
      dropEmptyStyle(el);
    } else if (e.kind === "class") {
      for (const c of e.added) if (el.classList.contains(c)) { el.classList.remove(c); reverted++; } else skipped++;
      for (const c of e.removed) if (!el.classList.contains(c)) { el.classList.add(c); reverted++; } else skipped++;
    } else if (e.kind === "attr") {
      const name = e.name;                                  // уже перевірене `attrAllowed` у setAttr
      if (stillOurs(el.getAttribute(name), e.after)) {
        if (e.before === null) el.removeAttribute(name); else el.setAttribute(name, e.before);
        reverted++;
      } else skipped++;
    } else if (stillOurs(el.textContent, e.after)) { el.textContent = e.before; reverted++; } else skipped++;
    return { reverted, skipped };
  }
  function revertSafe(e) {
    try { return revertEntry(e); } catch { return { reverted: 0, skipped: 1 }; }   // збій в одному записі не губить решту
  }

  // ---------- слухання дій користувача ----------
  const HOVER_MS = 100;
  let onClick = null, onOver = null, hoverLast = null, hoverSent = null, hoverTimer = 0, hoverAt = 0;
  const targetOf = (ev) => {
    let t = ev.target;
    if (t && t.nodeType === 3) t = t.parentElement;
    if (!t || t.nodeType !== 1 || pickState || isOurs(t) || !inBody(t)) return null;
    return t;
  };
  function emitHover() {
    hoverTimer = 0;
    const el = hoverLast;
    if (!alive || !el || el === hoverSent || !el.isConnected) return;
    hoverSent = el; hoverAt = Date.now();
    onEvent("page-hover", { node: describe(el) });
  }
  function setClick(on) {
    if (on && !onClick) {
      onClick = (ev) => {
        const el = targetOf(ev);
        if (el) onEvent("page-click", { node: describe(el), x: ev.clientX, y: ev.clientY, button: ev.button,
          alt: ev.altKey, shift: ev.shiftKey, meta: ev.metaKey, ctrl: ev.ctrlKey });
      };
      doc.addEventListener("click", onClick, { capture: true, passive: true });
    } else if (!on && onClick) { doc.removeEventListener("click", onClick, { capture: true }); onClick = null; }
  }
  function setHover(on) {
    if (on && !onOver) {
      onOver = (ev) => {
        const el = targetOf(ev);
        if (!el) return;
        hoverLast = el;
        if (el === hoverSent || hoverTimer) return;
        const wait = HOVER_MS - (Date.now() - hoverAt);
        if (wait <= 0) emitHover(); else hoverTimer = win.setTimeout(emitHover, wait);   // остання подія не губиться
      };
      doc.addEventListener("mouseover", onOver, { capture: true, passive: true });
    } else if (!on && onOver) {
      doc.removeEventListener("mouseover", onOver, { capture: true }); onOver = null;
      if (hoverTimer) { win.clearTimeout(hoverTimer); hoverTimer = 0; }
      hoverLast = hoverSent = null;
    }
  }

  function revertAllNow() {
    const sum = { reverted: 0, skipped: 0 };
    for (const e of journal.takeAll()) { const r = revertSafe(e); sum.reverted += r.reverted; sum.skipped += r.skipped; }
    return sum;
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
      if (selector.includes("\\")) throw new PageError("bad-args", "selector: escapes are not supported; use attribute selectors");
      if ((selector.match(/\(/g) || []).length > PARENS_MAX) throw new PageError("bad-args", `selector: at most ${PARENS_MAX} parentheses`);
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
      ensureHost();                                         // мертві коробки (хост прибрала сторінка) не рахуються в ліміт
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
      ensureHost();
      let id = own;
      if (!id) for (const [k, m] of marks) if (m.temp && m.el.deref() === el) { id = k; break; }   // та сама тимчасова — перезапуск
      if (!id && tempCount() < TEMP_MAX) id = addMark(el, "info", "", true);                         // без мітки — тимчасова рамка
      el.scrollIntoView({ block: "center", inline: "nearest", behavior: reduced ? "auto" : "smooth" });
      if (!id) return null;                                 // понад межу тимчасових: лише прокрутка
      const m = marks.get(id);
      m.box.classList.remove("fl"); void m.box.offsetWidth; m.box.classList.add("fl");
      if (m.timer) win.clearTimeout(m.timer);
      m.timer = win.setTimeout(() => { m.timer = 0; if (own) m.box.classList.remove("fl"); else dropMark(id); }, FLASH_MS);
      return null;
    },
    setStyle(ref, map) {
      const el = elOf(ref);
      const { ok, rejected } = checkStyleMap(map);
      const items = [], applied = [];
      const hadStyle = el.hasAttribute("style");
      if (ok.length) notFull();
      for (const [p, v] of ok) {
        const before = styleNow(el, p);
        if (v === null) el.style.removeProperty(p);
        else { el.style.removeProperty(p); el.style.setProperty(p, v, "important"); }
        const after = styleNow(el, p);
        if (v !== null && after.v === "") { putStyle(el, p, before); rejected.push(p); continue; }   // браузер не прийняв
        items.push({ p, before, after }); applied.push(p);
      }
      if (!items.length) {
        if (!hadStyle) dropEmptyStyle(el);
        return { id: null, applied: [], rejected };
      }
      return { id: journal.add({ kind: "style", el: new WeakRef(el), items }), applied, rejected };
    },
    setClass(ref, ch) {
      const el = elOf(ref);
      const add = checkClassList(ch?.add ?? []), remove = checkClassList(ch?.remove ?? []);
      const added = [...new Set(add)].filter((c) => !el.classList.contains(c));
      const removed = [...new Set(remove)].filter((c) => el.classList.contains(c) && !added.includes(c));
      if (!added.length && !removed.length) return { id: null };
      notFull();
      for (const c of removed) el.classList.remove(c);
      for (const c of added) el.classList.add(c);
      return { id: journal.add({ kind: "class", el: new WeakRef(el), added, removed }) };
    },
    setAttr(ref, name, value) {
      const el = elOf(ref);
      if (!attrAllowed(name)) throw new PageError("not-allowed", `attribute ${String(name).slice(0, 40)} is not allowed`);
      const v = checkAttrValue(value);
      notFull();
      const before = el.getAttribute(name);
      if (v === null) el.removeAttribute(name); else el.setAttribute(name, v);
      const after = el.getAttribute(name);
      return { id: journal.add({ kind: "attr", el: new WeakRef(el), name, before, after }) };
    },
    setText(ref, text) {
      const el = elOf(ref);
      if (el.children.length) throw new PageError("not-leaf", "the element has child elements");
      const t = checkText(text);
      notFull();
      const before = el.textContent;
      el.textContent = t;
      const after = el.textContent;
      return { id: journal.add({ kind: "text", el: new WeakRef(el), before, after }) };
    },
    revert(id) {
      live();
      const e = typeof id === "string" ? journal.take(id) : null;
      return e ? revertSafe(e) : { reverted: 0, skipped: 0 };
    },
    revertAll() {
      live();
      return revertAllNow();
    },
    listen(o = {}) {
      live();
      const click = o?.click, hover = o?.hover;
      for (const [k, v] of [["click", click], ["hover", hover]]) if (v !== undefined && typeof v !== "boolean") throw new PageError("bad-args", `${k}: a boolean`);
      if (click !== undefined) setClick(click);
      if (hover !== undefined) setHover(hover);
      return null;
    },
    pick() { return startPick(); },
    cancelPick() { finishPick(null); },
    get picking() { return !!pickState; },
    destroy() {
      if (!alive) return;
      if (doc.defaultView) revertAllNow();                  // поки документ живий
      setClick(false); setHover(false);
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
