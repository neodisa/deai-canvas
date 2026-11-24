/**
 * Помічник ядра для модулів (М2): ЧИСТІ правила без DOM — які методи моста вимагають якого дозволу, ліміти, що можна
 * міняти в документі макета. DOM-частина — `page-agent.js`, міст — `module-host.js`. Спека:
 * `docs/superpowers/specs/2026-11-24-modules-m2-page-helper-design.md`.
 */

export const PAGE_PERMS = ["read", "mark", "change", "listen"];

export const METHOD_PERM = {
  "page.info": "read", "page.query": "read", "page.get": "read", "page.snapshot": "read", "page.pick": "read",
  "page.reveal": "read",
  "page.mark": "mark", "page.unmark": "mark", "page.clearMarks": "mark",
  "page.setStyle": "change", "page.setClass": "change", "page.setAttr": "change", "page.setText": "change",
  "page.revert": "change", "page.revertAll": "change",
  "page.listen": "listen",
};

export const LIMITS = {
  queryDefault: 100, queryMax: 500, styles: 24, attrs: 30, attrVal: 300, nodeText: 300, cls: 200,
  snapshotDefault: 2000, snapshotMax: 4000, snapshotBytes: 2 * 1024 * 1024,
  marks: 300, label: 60, changes: 500, styleProps: 40, styleVal: 500, classes: 20, text: 2000,
};

export const TONES = ["error", "warn", "ok", "info"];
/** Кольори тонів — ті самі значення, що `--bad`, `--open`, `--ok`, `--pick` у `styles.css` (стереже тест): у документі
 *  макета токенів оболонки нема, тож літерали. */
export const TONE_COLORS = { error: "#F37373", warn: "#FBBC55", ok: "#6AD09D", info: "#3D8BFF" };

export class PageError extends Error {
  constructor(code, message) { super(message || code); this.code = code; }
}
const bad = (why) => new PageError("bad-args", why);

export const allowed = (method, perms) =>
  Object.hasOwn(METHOD_PERM, method) && Array.isArray(perms) && perms.includes(METHOD_PERM[method]);

const ATTR_PLAIN = new Set(["role", "hidden", "title", "alt", "lang", "dir", "tabindex", "disabled", "placeholder", "open"]);
const DATA_RESERVED = ["data-deai-", "data-canvas-", "data-comment-", "data-h2d-", "data-dc-"];
/** Службовий маркер ядра (`data-deai-*`, `data-canvas-*`, `data-comment-*`, `data-h2d-*`, `data-dc-*`): модуль його ні ставить,
 *  ні бачить в `attrs`. Єдине місце списку — тут. */
export function isCoreAttr(name) {
  if (typeof name !== "string") return false;
  const n = name.toLowerCase();
  return DATA_RESERVED.some((p) => n.startsWith(p));
}
/** Атрибут, який модуль може поставити чи зняти: лише безпечні для виконання й завантаження (без `on*`, `src`, `href`…). */
export function attrAllowed(name) {
  // Спершу сама назва: лише ASCII-нижній регістр (інакше `toLowerCase` зводить «K» Кельвіна до `k` і обходить перевірку).
  if (typeof name !== "string" || !/^[a-z][a-z0-9-]*$/.test(name)) return false;
  const n = name;
  if (ATTR_PLAIN.has(n)) return true;
  if (/^aria-[a-z]+(-[a-z]+)*$/.test(n)) return true;
  return /^data-[a-z0-9]+(-[a-z0-9]+)*$/.test(n) && !isCoreAttr(n);
}

const CLASS_RE = /^[A-Za-z_-][\w-]{0,99}$/;
export function checkClassList(list) {
  if (!Array.isArray(list) || list.length > LIMITS.classes) throw bad(`classes: a list of at most ${LIMITS.classes} names`);
  for (const c of list) if (typeof c !== "string" || !CLASS_RE.test(c)) throw bad(`bad class name ${String(c).slice(0, 40)}`);
  return list.slice();
}

const PROP_RE = /^(--[A-Za-z0-9_-]{1,60}|-?[a-z][a-z-]{0,59})$/;
export function checkStyleNames(list) {
  if (list == null) return [];
  if (!Array.isArray(list) || list.length > LIMITS.styles) throw bad(`styles: a list of at most ${LIMITS.styles} names`);
  for (const p of list) if (typeof p !== "string" || !PROP_RE.test(p)) throw bad(`bad style name ${String(p).slice(0, 40)}`);
  return list.slice();
}

/** Значення, що змусило б сторінку щось вантажити, або з CSS-екрануванням (обхід перевірки) — у `rejected`. Без лівої
 *  межі навмисно: ловить і `-webkit-image-set(`, `-webkit-cross-fade(`, `-moz-element(`; `attr(` — бо разом із `data-*`
 *  дає типізований `url`. */
const LOADS_RE = /(url|src|image|image-set|cross-fade|element|attr)\s*\(/i;
export function checkStyleMap(map) {
  if (!map || typeof map !== "object" || Array.isArray(map)) throw bad("styles: an object {prop: value|null}");
  const keys = Object.keys(map);
  if (!keys.length || keys.length > LIMITS.styleProps) throw bad(`styles: 1 to ${LIMITS.styleProps} properties`);
  const ok = [], rejected = [];
  for (const p of keys) {
    if (!PROP_RE.test(p)) throw bad(`bad style name ${p.slice(0, 40)}`);
    const v = map[p];
    if (v === null) { ok.push([p, null]); continue; }
    if (v === "") throw bad(`style ${p}: an empty string is not allowed, use null to remove`);
    if (typeof v !== "string" || v.length > LIMITS.styleVal) throw bad(`style ${p}: a string of at most ${LIMITS.styleVal} characters or null`);
    if (v.includes("\\") || LOADS_RE.test(v)) { rejected.push(p); continue; }
    ok.push([p, v]);
  }
  return { ok, rejected };
}

export function checkText(text) {
  if (typeof text !== "string" || text.length > LIMITS.text) throw bad(`text: a string of at most ${LIMITS.text} characters`);
  return text;
}
export function checkAttrValue(v) {
  if (v === null) return null;
  if (typeof v !== "string" || v.length > LIMITS.attrVal) throw bad(`attribute value: a string of at most ${LIMITS.attrVal} characters or null`);
  return v;
}
/** Ярлик мітки: до `LIMITS.label` символів Unicode; довший — обрізаний трикрапкою (без «самотніх» сурогатів). */
export function checkLabel(label) {
  if (label === undefined || label === null) return "";
  if (typeof label !== "string") throw bad("label: a string");
  const chars = Array.from(label);
  return chars.length > LIMITS.label ? chars.slice(0, LIMITS.label - 1).join("") + "…" : label;
}
export function checkTone(tone) {
  if (tone === undefined || tone === null) return "info";
  if (!TONES.includes(tone)) throw bad(`tone: one of ${TONES.join(", ")}`);
  return tone;
}

/** Відкат повертає «було» лише коли зараз досі «стало»: змінене після модуля (скрипт сторінки, тюнер) не чіпаємо. */
export const stillOurs = (current, after) => current === after;

/** Журнал змін: `add` → id (`c1`…), `take(id)` → запис чи null, `takeAll()` → новіші першими (порядок відкату), `newer(id)` → новіші за `id` (найстаріші першими). */
export function createJournal(max = LIMITS.changes) {
  const items = new Map();
  let seq = 0;
  return {
    get size() { return items.size; },
    /** Повний — агент перевіряє ДО зміни документа; `add` кидає `too-many` лише як страховку. */
    get full() { return items.size >= max; },
    add(entry) {
      if (items.size >= max) throw new PageError("too-many", `at most ${max} active changes`);
      const id = `c${++seq}`;
      items.set(id, { ...entry, id });
      return id;
    },
    take(id) { const x = items.get(id) ?? null; if (x) items.delete(id); return x; },
    /** Живі записи, додані ПІСЛЯ `id`, найстаріші першими (самі обʼєкти журналу, не копії): потрібні для передачі шару.
     *  Викликати ДО `take(id)` — після нього id невідомий і відповідь порожня. */
    newer(id) {
      const out = [];
      let seen = false;
      for (const [k, v] of items) { if (seen) out.push(v); else if (k === id) seen = true; }
      return out;
    },
    takeAll() { const all = [...items.values()].reverse(); items.clear(); return all; },
  };
}
