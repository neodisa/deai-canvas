/**
 * Інструменти модулів в оболонці (api 2): чиста логіка без DOM — що показати в острівці й палітрі, які клавіші
 * займає модуль і як оболонка відповідає панелі-пісочниці (міст `app/module-kit/bridge.js`).
 * Усе, що торкається DOM і мережі (iframe, `/api/module-tool`, тост), передає `app.js` колбеками.
 */

import { ICONS } from "./icons.js";

/** Скільки інструментів модулів вміщає острівець (решта — лише в ⌘K і клавішею). */
export const MAX_ISLAND_TOOLS = 3;

/**
 * Одно-літерні клавіші ядра: `KEYS` (`shell-palette.js`) — C, I, H, + `M` (інспектор) і `P` (коментатор, старий режим):
 * їх слухають вендорні обробники в рамці, тож модуль їх не займає. Тест звіряє список із `KEYS`.
 */
export const CORE_KEYS = ["C", "H", "I", "M", "P"];

/** Ключ інструмента для `data-val`, `modKeyMap` і ⌘K: «<модуль>/<інструмент>». */
export const modToolKey = (tool) => `${tool.module}/${tool.id}`;

const tools = (ext) => (ext && Array.isArray(ext.tools) ? ext.tools : []);
/** Іконка з маніфесту модуля: лише з набору ядра, інакше `puzzle` (`ico()` на невідомій кидає). */
const safeIcon = (name) => (typeof name === "string" && Object.hasOwn(ICONS, name) ? name : "puzzle");
const freeLetter = (tool, core) => (typeof tool.key === "string" && /^[A-Z]$/.test(tool.key) && !core.includes(tool.key) ? tool.key : null);

/** Інструменти для острівця: до `MAX_ISLAND_TOOLS`, лише екран задачі й «Макет». `letter` — лише вільна від ядра. */
export function islandModTools(ext, { screen, mode } = {}) {
  if (screen !== "task" || mode !== "layout") return [];
  return tools(ext).slice(0, MAX_ISLAND_TOOLS).map((x) => ({ key: modToolKey(x), label: x.label, icon: safeIcon(x.icon), letter: freeLetter(x, CORE_KEYS) }));
}

/** Усі інструменти для ⌘K (без ліміту острівця). */
export function paletteModTools(ext) {
  return tools(ext).map((x) => ({ key: modToolKey(x), label: x.label, icon: safeIcon(x.icon), letter: freeLetter(x, CORE_KEYS) }));
}

/** `{ЛІТЕРА: "<модуль>/<інструмент>"}` без літер ядра; на дубль літери виграє перший. */
export function modKeyMap(ext, coreKeys = CORE_KEYS) {
  const out = {};
  for (const x of tools(ext)) {
    const k = freeLetter(x, coreKeys);
    if (k && !Object.hasOwn(out, k)) out[k] = modToolKey(x);
  }
  return out;
}

const METHODS = ["hello", "context", "selection", "call", "toast", "close"];
const MAX_MSG = 65536;
const MAX_CALLS = 4;

const ok = (id, value) => ({ deai: 1, re: id, ok: true, value: value === undefined ? null : value });
const fail = (id, error, detail) => ({ deai: 1, re: id, ok: false, error, detail: String(detail ?? error).slice(0, 300) });

/**
 * Хост мосту: `handle(msg)` → відповідь панелі (або `null`, коли відповідати нема чим), `event(name, data)` → повідомлення-подія.
 * Модуль виклику хост НЕ бере з повідомлення: `callTool(fn, args)` уже привʼязаний до модуля відкритої панелі.
 * `hello` відповіді не має — викликач після нього шле подію `init` з `initData()`.
 */
export function createBridgeHost({ getContext, getSelection, getVars, getTheme, callTool, toast, close }) {
  let calls = 0;

  /** `null` — повідомлення придатне; інакше код відмови. Чуже (без `deai: 1` чи цілого `id`) — `"ignore"`. */
  function check(msg) {
    if (!msg || typeof msg !== "object" || msg.deai !== 1) return "ignore";
    if (!Number.isInteger(msg.id) || msg.id < 0) return "ignore";
    let size = Infinity;
    try { size = JSON.stringify(msg).length; } catch (e) { /* цикл — не передати */ }
    if (size > MAX_MSG) return "too-big";
    if (typeof msg.method !== "string" || (msg.args !== undefined && !Array.isArray(msg.args))) return "bad-message";
    if (!METHODS.includes(msg.method)) return "unknown-method";
    return null;
  }

  async function handle(msg) {
    const bad = check(msg);
    if (bad === "ignore") return null;
    const id = msg.id;
    if (bad) return fail(id, bad, bad === "unknown-method" ? msg.method : bad);
    const args = msg.args || [];
    try {
      switch (msg.method) {
        case "hello": return null;
        case "context": return ok(id, getContext());
        case "selection": return ok(id, getSelection());
        case "call": {
          if (typeof args[0] !== "string") return fail(id, "bad-args", "fn must be a string");
          if (calls >= MAX_CALLS) return fail(id, "busy", "too many concurrent calls");
          calls += 1;
          try { return ok(id, await callTool(args[0], args[1])); } finally { calls -= 1; }
        }
        case "toast":
          if (typeof args[0] !== "string") return fail(id, "bad-args", "text must be a string");
          toast(args[0].slice(0, 200));
          return null;
        case "close": close(); return null;
        default: return fail(id, "unknown-method", msg.method);
      }
    } catch (e) {
      return fail(id, (e && e.code) || "error", e && e.message);
    }
  }

  return {
    check, handle,
    event: (name, data) => ({ deai: 1, event: name, data }),
    initData: () => ({ context: getContext(), theme: getTheme(), vars: getVars() }),
  };
}
