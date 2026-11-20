/**
 * Командні коментарі в ОПУБЛІКОВАНОМУ превʼю (0.32.0, етап Ж): права панель оболонки превʼю, та сама розмітка, що в Deai
 * (`commentsPanelHTML`), але з правами глядача з посиланням.
 *
 * Рішення власника (20.11.2026):
 *   · додавати може будь-хто з посиланням;
 *   · змінювати й видаляти — лише СВОЇ: «свій» = id, створений у ЦЬОМУ браузері (запис у localStorage в момент створення,
 *     колбек коментатора `onAdd`). Те саме імʼя в іншому браузері — чужий коментар;
 *   · закривати й відкривати знову — лише в Deai: тут для цього НЕМА ні кнопок, ні дій у реєстрі (`CMT_ACTS`);
 *   · імʼя питаємо один раз — перед першим додаванням (діалог оболонки), не при відкритті панелі;
 *   · `prompt()` у превʼю не буває ніколи: імʼя дає оболонка (`host.userName` у `PREVIEW_HOST_ARG`, `serve.py`): рамка читає
 *     localStorage, а коли він недоступний — `window.parent.__dcPreviewUser`, куди оболонка кладе введене імʼя;
 *   · як у Deai: панель відкрито й імʼя вже відоме — додавання вмикається одразу (відкрита панель = режим додавання); імені
 *     нема — панель лише читається, а «+» питає імʼя й вмикає режим. «+» лишається перемикачем (вимкнути, щоб клацати макет).
 *
 * ⛔ Це ІНТЕРФЕЙСНЕ обмеження, а не замок: публічний ключ у кожній сторінці технічно дозволяє все. Справжній замок — правила
 * на боці сховища (окрема задача, поза 0.32; див. спеку етапу Ж).
 *
 * Чому окремий модуль, а не рядки в `ext-shell.js`: логіка «свого» й імені чиста й перевіряється юнітом (`ownStore`),
 * а проводка DOM (`createExtComments`) тримається купи й не розпухає оболонку. Модуль їде в публічне превʼю байт у байт,
 * тож тягне лише чисті модулі (`comments-view.js`, `ask.js`): без `comment-news.js` — він тягне `overview-pins.js`.
 */
import { askForm } from "./ask.js";
import { openCount } from "./comments-model.js";
import { commentsPanelHTML } from "./comments-view.js";
import { esc } from "./esc.js";
import { t } from "./i18n.js";

/** Де коментатор тримає імʼя автора (спільне для оболонки й рамки — превʼю статичне, одного походження). */
export const USER_KEY = "comment-layer:user";
/** Префікс ключа «моїх» коментарів у localStorage; повний ключ — з каналом збірки. */
export const OWN_PREFIX = "dc-own:";
/** Посилки коментатора з рамки, які панель приймає (`PREVIEW_HOST_ARG`). */
export const CMT_EVENTS = new Set(["ready", "change", "select", "mode", "add"]);
/** Що можна глядачеві: «Показати» всім; змінити/видалити — своїм; закритим — нічого. Закрити/відкрити/доручити тут немає зовсім. */
export const PREVIEW_ACTIONS = { any: ["cmtshow", "cmtshot"], own: ["cmtedit", "cmtdel"], closed: [] };
/** Дії панелі, які оболонка перекладає в `EXT_ACTIONS`. Закрити/відкрити знову/доручити/перенести — свідомо поза цим переліком. */
export const CMT_ACTS = ["comments", "cmtadd", "cmtshow", "cmtshot", "cmtedit", "cmteditsave", "cmteditcancel", "cmtdel", "cmtdelyes",
  "cmtdelno", "cmtsec", "cmtpins"];

/** Імʼя з сирого значення: порожнє й старе службове «Anonymous» (до 0.32 рамка писала його після скасованого `prompt()`) — не імʼя. */
export function cleanName(raw) {
  const v = String(raw == null ? "" : raw).trim();
  return v === "Anonymous" ? "" : v;
}

/** Імʼя автора: сховище, а коли воно недоступне чи порожнє — те, що оболонка тримає в памʼяті (`fallback()`). */
export function readNameFrom(getStorage, fallback) {
  let v = "";
  try { v = cleanName(getStorage().getItem(USER_KEY)); } catch (e) { v = ""; }
  return v || cleanName(fallback());
}

/** Чи можна глядачеві змінити/видалити коментар: він СВІЙ і ВІДКРИТИЙ у поточному знімку (закритим — ніколи, хоч би й підробили `data-val`). */
export function canTouch(own, snap, id) {
  if (!own.has(id)) return false;
  const c = snap && Array.isArray(snap.comments) ? snap.comments.find((x) => x && x.id === id) : null;
  return !!c && c.status !== "resolved";
}

/** Скільки останніх id авторства пам'ятаємо; більше — старі випадають (браузер не мусить рости від років коментування). */
const OWN_MAX = 500;
const ID_MAX = 200;

/**
 * «Мої» коментарі в браузері глядача. `getStorage()` — функція, а не сховище: у пісочниці (локальна копія, непрозорий
 * origin) сам доступ до `localStorage` КИДАЄ, і такий виняток мусить ловитись тут, а не під час створення модуля.
 * Сховище недоступне — «моїх» з нього нема (нічого не вгадуємо); ids, створені в ЦІЙ сторінці, лишаються в памʼяті.
 */
export function ownStore(getStorage, key) {
  const mem = new Set();
  const stored = () => {
    try {
      const v = JSON.parse(getStorage().getItem(key));
      return Array.isArray(v) ? v.filter((x) => typeof x === "string") : [];
    } catch (e) { return []; }
  };
  return {
    /** Знімок «моїх» (набір): на один перемальований список — одне читання сховища. */
    all: () => new Set([...stored(), ...mem]),
    has: (id) => typeof id === "string" && (mem.has(id) || stored().includes(id)),
    add(id) {
      if (typeof id !== "string" || !id || id.length > ID_MAX) return false;
      mem.add(id);
      const ids = stored();
      if (!ids.includes(id)) {
        ids.push(id);
        try { getStorage().setItem(key, JSON.stringify(ids.slice(-OWN_MAX))); } catch (e) { /* лише памʼять сторінки */ }
      }
      return true;
    },
  };
}

/** Поле вводу чи contenteditable: клавіші оболонки тоді не наші. */
function typingIn(ev, doc) {
  const isEd = (n) => !!n && n.nodeType === 1 && (/^(input|textarea|select)$/i.test(n.localName || "") || !!n.isContentEditable);
  const o = (typeof ev.composedPath === "function" && ev.composedPath()[0]) || ev.target;
  let a = null;
  try {
    a = doc?.activeElement || null;
    while (a && a.shadowRoot && a.shadowRoot.activeElement) a = a.shadowRoot.activeElement;
  } catch (e) { a = null; }
  return isEd(o) || isEd(a);
}

/** Розмітка діалогу імені: стиль `askForm` (`.cv-ask--form`) — одне поле, «Зберегти» / «Скасувати». */
function nameFormHTML() {
  return `<form class="cv-form" data-form="name" novalidate role="dialog" aria-modal="true" aria-labelledby="nm-h">`
    + `<h2 class="cv-form-h" id="nm-h">${esc(t("prevNameQ"))}</h2>`
    + `<div class="cv-field"><input id="nm-in" name="name" type="text" maxlength="60" autocomplete="off" spellcheck="false"`
    + ` aria-label="${esc(t("prevNameQ"))}" aria-describedby="cv-form-err" data-autofocus></div>`
    + `<p class="cv-form-err" id="cv-form-err" role="alert" data-form-error hidden></p>`
    + `<div class="cv-ask-row"><button type="button" data-a="cancel">${esc(t("askCancel"))}</button>`
    + `<button type="submit" data-a="ok">${esc(t("cmtSave"))}</button></div></form>`;
}

/**
 * Контролер панелі. `frame` — iframe з макетом; `mount` — `#cmt-panel`; `channel` — канал збірки (ключ «моїх»);
 * `onChange()` — оболонка перемальовує острівець (число відкритих, натиснута кнопка); `onOpen()` — панель ЩОЙНО відкрилась (кнопка,
 * C, чи вибір піна в макеті) — оболонка вимикає інспектор: вони взаємно виключні. Усе сховище — через функції:
 * `storage()` (за замовчуванням `localStorage`).
 */
export function createExtComments({ frame, mount, channel, onChange = () => {}, storage = () => localStorage, canToggle = () => true, onOpen = () => {} }) {
  const own = ownStore(storage, `${OWN_PREFIX}${channel || location.pathname}`);
  const st = {
    open: false, active: true, adding: false, ready: false, readyDoc: null, snap: null, sel: null, query: "",
    editing: null, draft: null, delAsk: null, expanded: { earlier: false, closed: false },
    wantAdd: false,
  };
  mount.setAttribute("aria-label", t("cmtTitle"));

  /** Живий коментатор рамки або `null`: рамка ще вантажиться, чужий документ, пісочниця (cross-origin кидає). */
  const layer = () => {
    if (!st.ready) return null;
    try {
      const L = frame.contentWindow && frame.contentWindow.CommentLayer;
      return L && typeof L.snapshot === "function" ? L : null;
    } catch (e) { return null; }
  };
  const readName = () => readNameFrom(storage, () => window.__dcPreviewUser);
  const visible = () => st.open && st.active;
  /** Додавання ввімкнене чи ось-ось увімкнеться (рамка ще вантажиться): для «+» і підказки порожньої панелі. */
  const armed = () => st.adding || st.wantAdd;

  function paint() {
    const ownIds = own.all();
    const html = visible() ? commentsPanelHTML({
      snapshot: st.snap, query: st.query, selectedId: st.sel, editingId: st.editing, delAsk: st.delAsk,
      expanded: st.expanded, filter: "all", dual: false, teamDown: null, fresh: null, down: null,
      isOwn: (c) => ownIds.has(c.id), actions: PREVIEW_ACTIONS, adding: armed(),
      emptyKey: armed() ? "cmtEmpty" : "cmtEmptyPlus",
    }) : "";
    /* Фокус і каретку поля пошуку / редагування — назад після перезапису (той самий прийом, що в `paintComments` Deai). */
    const act = document.activeElement;
    const inPanel = !!act && mount.contains(act);
    const cfmSel = inPanel && act.closest(".cmt-acts--cfm") ? `.cmt-acts--cfm .${act.classList.contains("cfm-yes") ? "cfm-yes" : "cfm-no"}` : null;
    const keep = inPanel && (act.id === "cmt-q" || act.classList.contains("cmt-edit"))
      ? { sel: act.id === "cmt-q" ? "#cmt-q" : ".cmt-edit", range: [act.selectionStart, act.selectionEnd] }
      : (cfmSel ? { sel: cfmSel, range: [0, 0] } : null);
    const top = mount.querySelector(".cmt-body")?.scrollTop || 0;
    mount.hidden = !html;
    document.body.classList.toggle("with-cmt", !!html);
    mount.innerHTML = html;
    const body = mount.querySelector(".cmt-body");
    if (body && top) body.scrollTop = top;
    if (st.editing && st.draft != null) { const ed = mount.querySelector(".cmt-edit"); if (ed) ed.value = st.draft; }
    if (keep) {
      const el = mount.querySelector(keep.sel);
      el?.focus();
      try { el?.setSelectionRange(...keep.range); } catch (e) { /* не текстове поле */ }
    }
    if (st.sel) mount.querySelector(`[data-cid="${CSS.escape(st.sel)}"]`)?.scrollIntoView({ block: "nearest" });
    onChange();
  }

  function reset({ sel = true } = {}) {
    if (sel) { st.sel = null; st.editing = null; st.draft = null; st.delAsk = null; }
  }

  /** Рамка втратила свого коментатора (нова адреса, чужий документ): старі картки з мертвими діями не лишаємо. */
  function dropFrame({ keepWant = false } = {}) {
    st.ready = false; st.readyDoc = null; st.snap = null; st.adding = false;
    if (!keepWant) st.wantAdd = false;
    reset();
    paint();
  }

  function setOpen(on) {
    on = !!on;
    if (st.open === on) return;
    st.open = on;
    if (on) onOpen();
    if (!on) {
      reset();
      if (st.adding) { try { layer()?.setCommentMode(false); } catch (e) { /* рамка пішла */ } }
      st.adding = false;
      st.wantAdd = false;
    } else if (st.active && readName()) {
      armOpen();
    }
    paint();
  }

  /** Як у Deai: відкрита панель = режим додавання, але лише коли імʼя вже відоме (без нього — тільки читання, «+» спитає). */
  function armOpen() {
    const L = layer();
    if (!L) { st.wantAdd = true; return; }       // рамка ще не відзвітувала: вмикаємо на її `ready`
    try { L.setCommentMode(true); st.adding = true; } catch (e) { st.wantAdd = false; }
  }

  /** Імʼя перед ПЕРШИМ коментарем: є — `true` одразу; нема — діалог оболонки; «Скасувати» — `false` (додавання не вмикаємо). */
  async function ensureName() {
    if (readName()) return true;
    const vals = await askForm(nameFormHTML, {
      focusBack: () => mount.querySelector('[data-act="cmtadd"]'),
      onSubmit: (v, ctl) => {
        const name = String(v.name || "").trim();
        if (!name) { ctl.focus("name"); return t("cnFieldRequired"); }
        window.__dcPreviewUser = name;       // рамці, якщо localStorage недоступний (`PREVIEW_HOST_ARG.userName`)
        try { storage().setItem(USER_KEY, name); } catch (e) { /* пісочниця: імʼя лише на цю сторінку */ }
        return undefined;
      },
    });
    return !!vals;
  }

  async function setAdding(on) {
    st.wantAdd = false;
    if (on) {
      if (!(await ensureName())) return;
      const L = layer();                      // ПІСЛЯ діалогу: за цей час рамка могла піти на іншу сторінку
      if (!L) return;
      L.setCommentMode(true);
      st.adding = true;
    } else {
      try { layer()?.setCommentMode(false); } catch (e) { /* рамка пішла */ }
      st.adding = false;
    }
    paint();
  }

  const ownGuard = (id) => canTouch(own, st.snap, id);

  const actions = {
    comments: () => setOpen(!st.open),
    cmtadd: () => setAdding(!armed()),
    cmtshow: (id) => { st.sel = id; try { layer()?.focus(id); } catch (e) { /* рамка пішла */ } paint(); },
    cmtsec: (k) => { if (k in st.expanded) { st.expanded[k] = !st.expanded[k]; paint(); } },
    cmtshot: (id) => { try { layer()?.openShot(id); } catch (e) { /* рамка пішла */ } },
    cmtpins: () => { try { layer()?.togglePins(); } catch (e) { /* рамка пішла */ } },
    /* Видалення й редагування — лише СВОЇХ: перевірка тут, а не лише в розмітці. Розмітку можна обійти (чужа картка
       без кнопки, але з дією в реєстрі), реєстр — ні. */
    cmtdel: (id) => {
      if (!ownGuard(id)) return;
      st.delAsk = id; paint(); mount.querySelector(".cmt-acts--cfm .cfm-no")?.focus();
    },
    cmtdelyes: (id) => {
      if (st.delAsk !== id || !ownGuard(id)) return;
      st.delAsk = null;
      try { layer()?.removeComment(id, { confirmed: true }); } catch (e) { /* рамка пішла */ }
      paint();
    },
    cmtdelno: () => closeDelAsk(true),
    cmtedit: (id) => {
      if (!ownGuard(id)) return;
      st.editing = id; st.draft = null; paint(); mount.querySelector(".cmt-edit")?.focus();
    },
    cmteditsave: () => {
      const id = st.editing;               // id з стану, а не з кнопки: `data-val` можна підробити
      if (!id || !ownGuard(id)) return;
      const ta = mount.querySelector(".cmt-edit");
      let ok = false;
      try { ok = !!layer()?.editComment(id, ta?.value); } catch (e) { ok = false; }
      if (ok) { st.editing = null; st.draft = null; }
      paint();
    },
    cmteditcancel: () => { st.editing = null; st.draft = null; paint(); },
  };

  function closeDelAsk(refocus) {
    const id = st.delAsk;
    st.delAsk = null;
    paint();
    if (refocus && id) mount.querySelector(`[data-act="cmtdel"][data-val="${CSS.escape(id)}"]`)?.focus();
  }

  /* Клік повз питання «Видалити назавжди?» — «ні», нічого не видаляючи (capture: раніше за інші кліки, що перемальовують). */
  document.addEventListener("click", (ev) => {
    if (st.delAsk && !ev.target.closest?.(".cmt-acts--cfm")) { st.delAsk = null; paint(); }
  }, true);
  /* Клік у макет — це клік в iframe: до `document` він не долітає, зате вікно оболонки втрачає фокус. */
  window.addEventListener("blur", () => setTimeout(() => {
    if (st.delAsk && document.activeElement?.tagName === "IFRAME") { st.delAsk = null; paint(); }
  }, 0));
  mount.addEventListener("input", (ev) => {
    if (ev.target.classList?.contains("cmt-edit")) { st.draft = ev.target.value; return; }
    if (ev.target.id !== "cmt-q") return;
    st.query = ev.target.value;
    paint();
  });
  /* ⌘/Ctrl+Enter зберігає редагування, Esc скасовує; `stopPropagation`, щоб Esc не пішов далі в оболонку. */
  mount.addEventListener("keydown", (ev) => {
    const ta = ev.target.closest?.(".cmt-edit");
    if (!ta) return;
    if (ev.key === "Enter" && (ev.metaKey || ev.ctrlKey)) { ev.preventDefault(); actions.cmteditsave(); }
    else if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); actions.cmteditcancel(); }
  });

  /** Посилка коментатора з рамки. ⛔ Джерело: `ev.source` — саме наша рамка І `ev.origin === location.origin`: рамка, що
   *  пішла на чужий сайт, лишається тим самим вікном, але її посилки — не наші (та сама межа, що в `app.js`). */
  function onMessage(ev) {
    if (ev.source !== frame.contentWindow || ev.origin !== location.origin) return;
    const m = ev.data;
    if (!m || m.type !== "dc-comments" || !CMT_EVENTS.has(m.ev)) return;
    /* `ev.source` не відрізняє документів (WindowProxy переживає навігацію): запізніла посилка СТАРОЇ сторінки після
       скидання не мусить повернути старих карток. Коментатор завжди шле `ready` до першого `change`. */
    if (!st.ready && m.ev !== "ready") return;
    if (m.ev === "ready") {
      st.ready = true;
      try { st.readyDoc = frame.contentDocument; } catch (e) { st.readyDoc = null; }
      const L = layer();
      try { st.snap = L ? L.snapshot() : null; } catch (e) { st.snap = null; }
      if (st.wantAdd) {
        st.wantAdd = false;
        if (visible() && readName() && L && !st.adding) armOpen();
      }
      paint();
    } else if (m.ev === "change") {
      if (m.snapshot && Array.isArray(m.snapshot.comments)) { st.snap = m.snapshot; paint(); }
    } else if (m.ev === "select") {
      st.sel = typeof m.id === "string" ? m.id : null;
      if (!st.open) { st.open = true; onOpen(); }
      paint();
    } else if (m.ev === "mode") {
      st.adding = !!m.on;
      paint();
    } else if (m.ev === "add") {
      own.add(m.id);
      paint();
    }
  }

  /** `C` у макеті (фокус у рамці) — як на оболонці. */
  function frameKey(ev) {
    if (ev.metaKey || ev.ctrlKey || ev.altKey || ev.shiftKey || ev.repeat || ev.isComposing) return;
    if (ev.defaultPrevented || !canToggle()) return;
    if (typingIn(ev, frame.contentDocument) || document.querySelector(".cv-ask-scrim, .cv-ask-pop")) return;
    if ((ev.key || "").toLowerCase() === "c" || ev.code === "KeyC") { ev.preventDefault(); ev.stopPropagation(); actions.comments(); }
  }

  /** Рамка завантажила документ. Не той, що надіслав `ready` (нова сторінка ще не відзвітувала), чи без коментатора — старі
   *  картки з мертвими діями скидаємо: нова сторінка надішле свій список сама. */
  function onFrameLoad() {
    let doc = null;
    let w = null;
    try { w = frame.contentWindow; doc = frame.contentDocument; w.addEventListener("keydown", frameKey, true); } catch (e) {
      dropFrame();                       // чужий документ чи пісочниця: коментатора там не дістати
      return;
    }
    /* `load` приходить РАНІШЕ за `ready` коментатора (той стартує асинхронно): відкладене «додавання» тут не скидаємо —
       його вмикає `ready` цього ж документа. Решту (картки, вибір) скидаємо. */
    if (!w.CommentLayer || st.readyDoc !== doc) dropFrame({ keepWant: true });
  }

  return {
    actions, onMessage, onFrameLoad, dropFrame, setOpen,
    toggle: () => actions.comments(),
    isOpen: () => visible(),
    isAdding: () => st.adding,
    count: () => openCount(st.snap),
    /** Вид без живого макета (огляд кадрів): панель ховаємо, режим додавання вимикаємо. */
    setActive(on) {
      on = !!on;
      if (st.active === on) return;
      st.active = on;
      if (!on && st.adding) { try { layer()?.setCommentMode(false); } catch (e) { /* рамка пішла */ } st.adding = false; }
      if (!on) st.wantAdd = false;
      paint();
    },
    own,
    /** Початкова розмітка (порожня, схована) — щоб `with-cmt` і розмітка були узгоджені до першої посилки. */
    paint,
  };
}
