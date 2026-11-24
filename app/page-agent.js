/**
 * Помічник ядра для модулів (М2): працює над документом рамки макета ЗІ СВОГО вікна (те саме походження) — як
 * інспектор і тюнер. Код модуля сюди не потрапляє: модуль лише просить через міст (`module-host.js`).
 * ⛔ Жоден рядок від модуля не йде в `innerHTML`/`insertAdjacentHTML`/`eval` чи атрибут поза `attrAllowed` —
 * лише `textContent`, `style.setProperty`, `classList`. Стереже статичний тест у `tests/page-rules.test.mjs`.
 * ⛔ Вузли — з ІНШОГО вікна: жодного `instanceof`, лише `nodeType`/`localName`.
 */
import { LIMITS, PageError, checkStyleNames } from "./page-rules.js";

const OURS = "[data-canvas-inspector],[data-comment-layer],#cl-down,[data-deai-marks]";
const SKIP = new Set(["script", "style", "template", "noscript"]);
const clip = (s, n) => (s.length > n ? s.slice(0, n) : s);
const round = (x) => Math.round(x * 10) / 10;

export function createPageAgent({ doc, onEvent = () => {}, pageInfo = () => null }) {
  const win = doc.defaultView;
  let alive = true;
  let seq = 0;
  const byEl = new WeakMap();
  const byRef = new Map();

  const live = () => { if (!alive || !doc.defaultView) throw new PageError("no-page", "no live mockup page"); };
  const isOurs = (el) => !!el.closest(OURS);
  const inBody = (el) => !!doc.body && doc.body.contains(el) && !el.closest("script,style,template,noscript");
  function refOf(el) {
    let r = byEl.get(el);
    if (!r) { r = `r${++seq}`; byEl.set(el, r); byRef.set(r, new WeakRef(el)); }
    return r;
  }
  function elOf(ref) {
    live();
    const el = typeof ref === "string" ? byRef.get(ref)?.deref() : null;
    if (!el || !el.isConnected || el.ownerDocument !== doc) throw new PageError("stale-ref", "the element is gone or the page reloaded");
    return el;
  }
  function ownText(el) {
    let s = "";
    for (const n of el.childNodes) if (n.nodeType === 3) s += n.nodeValue;
    return clip(s.replace(/\s+/g, " ").trim(), LIMITS.nodeText);
  }
  function attrsOf(el) {
    const out = {};
    for (const a of [...el.attributes].slice(0, LIMITS.attrs)) out[a.name] = clip(a.value, LIMITS.attrVal);
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
    if (o.styles && o.styles.length) { n.styles = {}; for (const p of o.styles) n.styles[p] = cs.getPropertyValue(p); }
    return n;
  }
  const opts = (o) => ({ styles: checkStyleNames(o?.styles), attrs: o?.attrs === true });
  function intIn(v, dflt, max, name) {
    if (v === undefined) return dflt;
    if (!Number.isInteger(v) || v < 1) throw new PageError("bad-args", `${name}: a positive integer`);
    return Math.min(v, max);
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
      if (typeof selector !== "string" || !selector || selector.length > 1000) throw new PageError("bad-args", "selector: a non-empty string");
      const limit = intIn(o?.limit, LIMITS.queryDefault, LIMITS.queryMax, "limit");
      const so = opts(o);
      let found;
      try { found = doc.querySelectorAll(selector); } catch (e) { throw new PageError("bad-selector", String(e?.message || e).slice(0, 200)); }
      const out = [];
      for (const el of found) {
        if (out.length >= limit) break;
        if (inBody(el) && !isOurs(el)) out.push(describe(el, so));
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
          const n = describe(el, so);
          n.parent = el === doc.body ? null : refOf(el.parentElement);
          bytes += JSON.stringify(n).length;
          if (nodes.length >= max || bytes > LIMITS.snapshotBytes) { truncated = true; break; }
          nodes.push(n);
        }
      }
      return { info: api.info(), truncated, nodes };
    },
    destroy() {
      if (!alive) return;
      alive = false;
      byRef.clear();
    },
  };
  return api;
}
