/**
 * Чиста модель відгуку (0.23.0): перевірка форми, тіла запитів, текст результату, вигляд «Що буде надіслано». Ні DOM, ні fetch, ні `t()` —
 * лише дані й ІМЕНА ключів словника (як `update-model.js`); текст складає `app.js`/`feedback-view.js`.
 *
 * Контракт сервера (`serve._feedback`, `serve._feedback_preview`): див. заголовок `app/feedback.py`. `text` 10..10000 після trim,
 * `contact` ≤ 200; `include_diag` за замовчуванням true, `include_shot` — false.
 */

export const TEXT_MIN = 10;
export const TEXT_MAX = 10000;
export const CONTACT_MAX = 200;
export const KINDS = ["bug", "idea"];

const len = (s) => Array.from(String(s ?? "")).length;

/** Ключ словника помилки форми або `null`. Довжини — у символах (code points), як на сервері. */
export function validate({ kind, text, contact } = {}) {
  if (!KINDS.includes(kind)) return "fbErrKind";
  const n = len(String(text ?? "").trim());
  if (n < TEXT_MIN) return "fbErrShort";
  if (n > TEXT_MAX) return "fbErrLong";
  if (len(String(contact ?? "").trim()) > CONTACT_MAX) return "fbErrContact";
  return null;
}

/** Поле форми, до якого належить помилка (для `ctl.focus`). */
export const errField = (key) => (key === "fbErrKind" ? "kind" : key === "fbErrContact" ? "contact" : "text");

/** Аргумент функції-підпису помилки (межа). */
export const errArg = (key) => (key === "fbErrShort" ? TEXT_MIN : key === "fbErrLong" ? TEXT_MAX : key === "fbErrContact" ? CONTACT_MAX : undefined);

/** Код відмови сервера (`400 {code}`) → ключ помилки поля; невідомий → `null` (загальна помилка). */
export function serverErrKey(code) {
  switch (code) {
    case "bad-kind": return "fbErrKind";
    case "text-too-short": return "fbErrShort";
    case "text-too-long": return "fbErrLong";
    case "bad-contact": case "contact-too-long": return "fbErrContact";
    default: return null;
  }
}

/**
 * Сесія діалогу. Контекст (`task, it, node, screen, lang`) і ЗНІМОК кільця помилок беруться ОДИН раз при створенні: попередній перегляд
 * і відправка читають ТОЙ САМИЙ масив `clientErrors` (рівно те, що людина бачила, те й піде; помилка, що зʼявилась, поки діалог відкритий,
 * у відгук не потрапляє непоміченою). `ctx.node` лише коли є кадр: без нього `it`/`node` не шлемо.
 */
export function createSession({ ctx = {}, clientErrors = [], lang = "uk" } = {}) {
  const errors = Array.isArray(clientErrors) ? clientErrors : [];
  const base = () => {
    const o = {};
    for (const k of ["task", "it", "node", "screen"]) if (typeof ctx[k] === "string" && ctx[k]) o[k] = ctx[k];
    o.lang = lang;
    return o;
  };
  return {
    clientErrors: errors,
    /** Тіло `POST /api/feedback-preview`. */
    previewBody: () => ({ ...base(), client_errors: errors }),
    /** Адреса знімка поточної сторінки (той самий `/shot`, що малює кадри) або `""`, коли `it`/`node` не названо. */
    shotUrl: () => {
      const b = base();
      return b.it && b.node ? `/shot?it=${encodeURIComponent(b.it)}&node=${encodeURIComponent(b.node)}` : "";
    },
    /** Тіло `POST /api/feedback`. `shotAvailable` — що сказав попередній перегляд; без кадру `include_shot` завжди `false`.
     *  `diagHash` — відбиток діагностики з ОСТАННЬОГО показаного перегляду: сервер звіряє його («що показано = що піде»). */
    sendBody: ({ kind, text, contact, includeDiag, includeShot, shotAvailable, diagHash }) => {
      const o = { kind, text: String(text ?? "").trim(), ...base(), client_errors: errors };
      const c = String(contact ?? "").trim();
      if (c) o.contact = c;
      o.include_diag = includeDiag !== false;
      if (typeof diagHash === "string" && diagHash) o.diag_hash = diagHash;
      o.include_shot = includeShot === true && shotAvailable === true;
      return o;
    },
  };
}

/** Стан чекбокса «знімок»: `{available, bytes, reasonKey}`. `reasonKey` — чому вимкнений. */
export function shotState(preview) {
  const s = preview && typeof preview === "object" && preview.shot && typeof preview.shot === "object" ? preview.shot : null;
  if (s && s.available === true) return { available: true, bytes: Number.isInteger(s.bytes) ? s.bytes : 0, reasonKey: null };
  return { available: false, bytes: 0, reasonKey: s && s.skipped === "too-big" ? "fbShotTooBig" : "fbShotNone" };
}

/** `409 {code:'diag-changed', diag, diag_hash, shot?}` → новий перегляд (його треба ПОКАЗАТИ й попросити натиснути «Надіслати» ще раз) або
 *  `null`, коли відповідь не така. Знімок бере зі старого перегляду, якщо сервер не прислав свого. */
export function previewFromConflict(prev, body) {
  const b = body && typeof body === "object" ? body : null;
  if (!b || b.code !== "diag-changed" || !b.diag || typeof b.diag !== "object" || typeof b.diag_hash !== "string") return null;
  const shot = b.shot && typeof b.shot === "object" ? b.shot : (prev && prev.shot) || { available: false };
  return { ok: true, diag: b.diag, diag_hash: b.diag_hash, shot };
}

/** Результат `POST /api/feedback` → `{key, args, suffixKey}`: ключ тосту, його аргументи й (для памʼяті-лише) додаток. */
export function outcome(res) {
  const r = res && typeof res === "object" ? res : {};
  const number = String(r.number ?? "");
  const suffixKey = r.memory_only === true ? "fbMemOnly" : null;
  if (r.state === "sent") return { key: "fbSent", args: [number], suffixKey: null };
  return { key: r.reason === "no-collector" ? "fbQueuedNoCollector" : "fbQueued", args: [number], suffixKey };
}

/** Стабільний (ключі за абеткою) відступний JSON — те, що людина читає в «Що буде надіслано». */
export function previewText(value) {
  const sort = (_k, v) => (v && typeof v === "object" && !Array.isArray(v)
    ? Object.fromEntries(Object.keys(v).sort().map((k) => [k, v[k]])) : v);
  return JSON.stringify(value, sort, 2);
}

/** Що піде разом з текстом при цих галочках: діагностика (або `{}`) і чи прикладено знімок. */
export function sentView(preview, { includeDiag, includeShot }) {
  const shot = shotState(preview);
  const attach = includeShot === true && shot.available;
  return {
    diag: includeDiag === false ? {} : ((preview && preview.diag) ?? {}),
    shot: attach ? { attached: true, bytes: shot.bytes } : { attached: false },
  };
}
