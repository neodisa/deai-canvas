/**
 * Коментарі на «Огляді» (T-45) — склейка оболонки з comment-layer у режимі
 * «полотно» (`init({anchors})`).
 *
 * Межа та сама, що в Claude Design: оболонка дає координати й камеру,
 * коментатор малює все своє — піни, прев'ю, панель, вкладки «Клод/Команда».
 * Уся математика — в `overview-pins.js` (чиста, під юнітами); тут лише стан,
 * мережа й життєвий цикл інстансу.
 *
 * Звідки точка піна: геометрія кадру (`/shot-geo`), яку зняв ЗАТВОР у тій самій
 * розкладці, що дала пікселі (`bin/shots-geo.mjs`), і `findMatchIn` — той самий
 * алгоритм, що `findMatch` у живому виді. Прихованої копії сторінки тут немає
 * свідомо: вона не повторила б стану затвора, а важкий документ у головному
 * потоці смикав би панораму.
 */
import { HEAD } from "./canvas-geom.js";
import { t } from "./i18n.js";
import { stateQuery } from "./flow-model.js";
import { cardAt, cardsOfPin, hitElement, layoutPins, pinWorld, revealCam, targetFor } from "./overview-pins.js";

const SB_JS = "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2";
const ENRICH_MS = 8000;       // стеля збагачення — та сама, що в comment-layer на скриншот
const MAX_OUTER_HTML = 6000;  // як `context-bundle.js`: рядок у Supabase не росте
const SHOT_MAX_W = 360;       // як скриншот DOM-режиму
const GEO_RETRY_MS = 5000;    // мережевий збій геометрії — повтор, а не вирок «поза кадром»

const sleep = (ms) => new Promise((ok) => { setTimeout(ok, ms); });
const normText = (s) => (s || "").replace(/\s+/g, " ").trim();

/** Елемент за шляхом відбитка (`['div[0]','p[2]']` — тег і індекс серед
 *  братів з тим самим тегом, від body), рівно як `tagPath` його рахує. */
function byPath(root, path) {
  let n = root;
  for (const seg of path || []) {
    const m = /^([a-z0-9-]+)\[(\d+)\]$/i.exec(seg);
    if (!m || !n) return null;
    const sibs = [...n.children].filter((c) => c.tagName.toLowerCase() === m[1]);
    n = sibs[Number(m[2])] || null;
  }
  return n === root ? null : n;
}

function loadScript(src) {
  return new Promise((ok, no) => {
    const s = document.createElement("script");
    s.src = src;
    s.onload = ok;
    s.onerror = () => no(new Error(t('errScriptLoad', src)));
    document.head.appendChild(s);
  });
}

/** id модуля → фабрика його адаптера (`window.DeaiComments`, захоплена ОДРАЗУ після завантаження його файлів). */
const FACTORIES = new Map();

/**
 * Сховище командного каналу МОДУЛЯ для відповіді `/api/comment-config?ch=project` із полем `module` (2b-2): файли
 * адаптера (`cfg.client`, кореневі адреси) вантажаться ПО ПОРЯДКУ — кожен чекаємо, бо наступний може спиратись на
 * попередній (бібліотека, потім адаптер) — без дублів у списку; далі `DeaiComments.create({...config, channel, onChange})`.
 *
 * ⛔ Фабрику кешуємо ЗА МОДУЛЕМ, а не лишаємо в глобалі: адаптер кожного модуля пише в той самий
 * `window.DeaiComments`, тож після двох модулів по черзі (перемикання просторів) повернення до першого взяло б чужу
 * фабрику — командні коментарі пішли б у чужий сервіс. І перед завантаженням глобал скидається: адаптер, що фабрики не
 * зареєстрував, не повинен підхопити залишок попереднього модуля.
 *
 * `channel` і `onChange` — ядра: модуль не перекриє їх ключами свого `config`. `onChange` порожній: шар коментатора живе
 * через `store.subscribe`. Невдача (файл не завантажився, фабрики нема, `create` кинув) — виняток викликачу; нічого не
 * кешується, тож наступний вхід в «Огляд» спробує знову, а сам «Огляд» без пінів працює.
 * @param cfg {{module: string, client?: string[], config?: object, channel: string}}
 */
export async function moduleStore(cfg, { load = loadScript, win = window, factories = FACTORIES } = {}) {
  let factory = factories.get(cfg.module);
  if (!factory) {
    delete win.DeaiComments;
    for (const src of new Set(Array.isArray(cfg.client) ? cfg.client : [])) await load(src);
    factory = win.DeaiComments;
    if (!factory || typeof factory.create !== "function") throw new Error(t("errCommentsAdapter"));
    factories.set(cfg.module, factory);
  }
  return factory.create({ ...(cfg.config || {}), channel: cfg.channel, onChange: () => {} });
}

/**
 * @param env {{
 *   canvasEl: Element, cam: () => {x,y,scale}, cards: () => Array, cardW: () => number,
 *   picked: () => string|null, channel: () => 'local'|'project',
 *   frameKeyOf: (card) => string, shotOf: (card) => object|null,
 *   camTo: (target) => void, focusCard: (card) => void,
 *   audiences: () => Array, onAudience: (ch) => void, fail: (err) => void,
 * }} env
 */
export function overviewComments(env) {
  let cl = null;        // інстанс comment-layer (`CommentLayer.create()`)
  let cfgKey = null;    // `<ітерація>|<канал>` — під яким він піднятий
  let active = false;   // «Огляд» на екрані
  let view = null;      // габарит полотна в екранних координатах
  let iterNum = null;   // тег ітерації каналу (`cfg.version`) — для тегу версії нового піна
  const subs = [];
  let inflight = null;  // ensure() у дорозі — другий виклик чекає ЙОГО, а не піднімає свій інстанс
  /** fkey → { sha, els } | 'loading'. `sha` — версія КАДРУ: перезняли кадр —
   *  геометрія під ним інша, і стара мусить піти разом зі старим знімком.
   *  `els: null` — невдача САМЕ для цієї версії: не смикаємо сервер щокадру, але
   *  перезнятий кадр (інший `sha`) спробує знову. */
  const geo = new Map();
  /** pin → Map(`fkey|sha` → запис геометрії|null) — ЯКИЙ елемент, без позиції
   *  кадру: точка з нього рахується щоразу (арифметика), тож перетягування вузла
   *  флоу не плодить записів (ревʼю T-45, D6). WeakMap по ОБʼЄКТУ піна: нові
   *  обʼєкти сховища скидають кеш самі. */
  const entryCache = new WeakMap();

  const measure = () => {
    const r = env.canvasEl.getBoundingClientRect();
    view = { left: r.left, top: r.top, w: r.width, h: r.height };
  };
  const tick = () => { if (active) for (const fn of subs) fn(); };
  addEventListener("resize", () => { if (active) { measure(); tick(); } });

  /**
   * Геометрія кадру: `{sha, els}` — є; `undefined` — ЩЕ не знаємо (їде, або кадр
   * знято до T-45 і він чекає тихої перезйомки); `null` — ВІДОМО, що нема (кадру
   * нема, затвор не зміг — `geoProblem`, сервер відмовив). Різниця несуча:
   * «невідомо» не рахується ні на кадрі, ні «поза кадром», а «нема» — поза кадром.
   */
  function geoOf(card) {
    const shot = env.shotOf(card);
    /* Кадру ще нема (перший візит — автозйомка T-34 якраз знімає) — це
       «невідомо», не «нема»: інакше до кінця прогону на заглушках блимало
       «поза кадром: 7» (повторне ревʼю, NEW-1). */
    if (!shot) return undefined;
    if (shot.geoProblem) return null;
    if (!shot.geo) return undefined;
    const fkey = env.frameKeyOf(card);
    const g = geo.get(fkey);
    if (g === "loading") return undefined;
    if (g && g.sha === shot.sha) {
      if (g.els) return g;
      // мережа впала — не «нема», а «спробуй пізніше» (NEW-3); 404 — справді нема
      if (!g.retryAt) return null;
      if (Date.now() < g.retryAt) return undefined;
    }
    geo.set(fkey, "loading");
    const it = env.picked();
    fetch(`/shot-geo?it=${encodeURIComponent(it)}&node=${encodeURIComponent(fkey)}`
          + `&v=${encodeURIComponent(shot.sha || "")}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { geo.set(fkey, { sha: shot.sha, els: d && Array.isArray(d.els) ? d.els : null }); tick(); })
      .catch(() => {
        geo.set(fkey, { sha: shot.sha, els: null, retryAt: Date.now() + GEO_RETRY_MS });
        // камера може стояти — повтор мусить прийти сам, а не чекати руху
        setTimeout(tick, GEO_RETRY_MS + 50);
      });
    return undefined;
  }

  /** Світова точка піна: `{x,y}` | `null` (відомо: місця нема) | `undefined` (ще не знаємо). */
  function worldOf(pin, card) {
    const g = geoOf(card);
    if (!g) return g;   // undefined | null — див. geoOf
    let m = entryCache.get(pin);
    if (!m) { m = new Map(); entryCache.set(pin, m); }
    const k = `${env.frameKeyOf(card)}|${g.sha}`;
    if (!m.has(k)) {
      const A = window.CommentLayerAnchor;
      const hit = A.findMatchIn(pin.fp, g.els);
      m.set(k, hit.i >= 0 && hit.score >= A.MATCH_THRESHOLD ? g.els[hit.i] : null);
    }
    const e = m.get(k);
    return e ? pinWorld(card, e, pin.meta && pin.meta.anchor, HEAD) : null;
  }

  const provider = {
    mount: env.canvasEl,
    active: () => active,
    // верх полотна у вікні: панель коментатора не сміє ховати шапку під смугою
    top: () => (view ? view.top : 0),
    subscribe: (fn) => { subs.push(fn); },
    place: (pins) => {
      if (!active || !view) return [];
      const items = layoutPins({ pins, cards: env.cards(), cam: env.cam(), cardW: env.cardW(), view, worldOf });
      for (const it of items) if (it.off) it.label = env.offLabel(it.ids.length);
      return items;
    },
    reveal: (c) => {
      const mine = cardsOfPin(c, env.cards());
      for (const card of mine) {
        const w = worldOf(c, card);
        if (w) { env.camTo(revealCam(w, env.cam(), view)); return; }
      }
      // Точки немає (кадр без геометрії чи елемент зник) — летимо хоча б до
      // КАДРУ його сторінки: тиша на клік виглядала б зламаною фічею.
      if (mine.length) env.focusCard(mine[0]);
    },
    revealKey: (key) => {
      const card = env.cards().find((k) => `k:${k.id}` === key);
      if (card) env.focusCard(card);
    },
    // ── етап 2: створення на полотні ──
    hit: (x, y) => {
      if (!active || !view || iterNum == null) return null;
      /* Під курсором мусить бути САМ кадр, а не UI оболонки над ним (смуга,
         панелі, підказка) і не шар коментатора. Без цього кадр, зсунутий під
         смугу, «підсвічувався» крізь неї, а клік по «Макет» ковтався
         композером (ревʼю T-45, D4). */
      const top = document.elementFromPoint(x, y);
      if (!top || !env.canvasEl.contains(top) || !top.closest(".cv-card-body")) return null;
      const cam = env.cam();
      const wx = (x - view.left - cam.x) / cam.scale, wy = (y - view.top - cam.y) / cam.scale;
      const at = cardAt(env.cards(), wx, wy, env.cardW(), HEAD);
      if (!at) return null;
      const g = geoOf(at.card);
      if (!g) return null;   // геометрія ще їде (або кадру без неї) — підсвітки нема, клік хоста
      const i = hitElement(g.els, at.lx, at.ly);
      if (i < 0) return null;
      return targetFor({ card: at.card, e: g.els[i], lx: at.lx, ly: at.ly, cam, view, head: HEAD,
        it: env.picked(), iterNum, channel: env.channel(), canvasW: env.cardW(), origin: location.origin });
    },
    armed: (on) => env.onArmed(on),
    enrich: (t) => enrich(t),
    shot: (t) => Promise.resolve(cropShot(t)),
  };

  /**
   * Повний відбиток і HTML елемента з живої bare-сторінки ТІЄЇ Ж ширини. Геометрія
   * несе текст зрізаним (2000) і без `outerHTML`, а Клоду HTML потрібен у
   * контексті. Прихована рамка вантажиться ОДИН раз на коментар і лише поки
   * людина друкує. Елемент шукаємо за шляхом і звіряємо з геометрією: сторінка
   * могла змінитись від кадру — тоді лишаємо відбиток із геометрії (fail-soft).
   */
  function enrich(t) {
    return new Promise((done) => {
      const f = document.createElement("iframe");
      f.setAttribute("aria-hidden", "true");
      f.tabIndex = -1;
      f.style.cssText = `position:fixed;left:-20000px;top:0;width:${env.cardW()}px;height:900px;`
        + "border:0;visibility:hidden;pointer-events:none";
      let over = false;
      const finish = (v) => { if (over) return; over = true; clearTimeout(timer); f.remove(); done(v); };
      const timer = setTimeout(() => finish(null), ENRICH_MS);
      f.onload = async () => {
        try {
          const body = f.contentWindow.document.body;
          let el = null;
          // SPA домальовується ПІСЛЯ load — чекаємо шлях до ~3с
          for (let i = 0; i < 30 && !el; i += 1) { el = byPath(body, t.fp.path); if (!el) await sleep(100); }
          if (!el) { finish(null); return; }
          const fp = window.CommentLayerAnchor.fingerprint(el, body);
          if (fp.textHash !== t.fp.textHash && fp.structHash !== t.fp.structHash) { finish(null); return; }
          const outer = el.outerHTML || "";
          finish({ fp, htmlSnapshot: {
            outerHTML: outer.length <= MAX_OUTER_HTML ? outer : `${outer.slice(0, MAX_OUTER_HTML)}…[truncated]`,
            text: normText(el.textContent).slice(0, 500) } });
        } catch { finish(null); }
      };
      f.src = `/commented?it=${encodeURIComponent(env.picked())}&page=${encodeURIComponent(t.card.page)}`
        + `&bare=1${stateQuery(t.card.state)}`;
      document.body.appendChild(f);
    });
  }

  /** Скриншот картки — виріз ІЗ САМОГО кадру: пікселі 1:1 з тим, що бачить
   *  людина, без повторного рендеру (html2canvas DOM-режиму тут нема чого рендерити). */
  function cropShot(t) {
    const img = t.card.el && t.card.el.querySelector(".cv-card-body img");
    if (!img || !img.complete || !img.naturalWidth) return null;
    const e = t.geo, pad = 16;
    const sx = Math.max(0, e.x - pad), sy = Math.max(0, e.y - pad);
    const sw = Math.min(img.naturalWidth - sx, e.w + pad * 2), sh = Math.min(img.naturalHeight - sy, e.h + pad * 2);
    if (!(sw > 0 && sh > 0)) return null;
    const k = Math.min(1, SHOT_MAX_W / sw);
    const c = document.createElement("canvas");
    c.width = Math.max(1, Math.round(sw * k)); c.height = Math.max(1, Math.round(sh * k));
    c.getContext("2d").drawImage(img, sx, sy, sw, sh, 0, 0, c.width, c.height);
    return c.toDataURL("image/jpeg", 0.6);
  }

  const keyNow = () => `${env.picked()}|${env.channel()}`;

  /**
   * Інстанс коментатора під поточні ітерацію й канал. ⛔ Кличуть ДВІЧІ поспіль
   * (`buildCanvas` → `rebuild`, потім `applyMode` → `enter`), і поки перший
   * виклик чекав мережі, `cl` був порожній — другий піднімав ДРУГИЙ інстанс, а
   * старий на перемиканні каналу не знищувався. Осиротілий ловив `C` і писав
   * «Клода» в канал «Команди» (ревʼю T-45, D1). Тепер виклик у дорозі — спільний.
   */
  async function ensure() {
    if (!env.picked()) return;
    const key = keyNow();
    if (cfgKey === key && (cl || inflight)) return inflight;
    if (cl) { cl.destroy(); cl = null; subs.length = 0; }
    cfgKey = key;
    const run = start(key);
    inflight = run;
    try { await run; }
    catch (e) {
      /* Падіння ЗАСТАРІЛОГО запуску (канал уже перемкнули) — не наша справа:
         скинути `cfgKey` означало б обнулити поточний запуск, і той тихо
         вийшов би на `cfgKey !== key` без жодного інстансу (NEW-2). */
      if (cfgKey !== key) return;
      cfgKey = null;
      throw e;
    } finally { if (inflight === run) inflight = null; }
  }

  async function start(key) {
    const [it, ch] = key.split("|");
    const cfg = await fetch(`/api/comment-config?ch=${encodeURIComponent(ch)}&it=${encodeURIComponent(it)}`)
      .then((r) => { if (!r.ok) throw new Error(`comment-config ${r.status}`); return r.json(); });
    if (cfgKey !== key) return;   // поки чекали — перемкнули канал чи ітерацію
    let store;
    if (cfg.module) {
      // Командний канал веде модуль ролі `comments`: його адаптер, а не зашитий Supabase ЛІГА.
      store = await moduleStore(cfg);
    } else if (cfg.ch === "project") {
      if (!window.supabase) await loadScript(SB_JS);
      store = window.CommentLayerSupabase({ url: cfg.sbUrl, anonKey: cfg.sbKey, projectId: cfg.project });
    } else {
      store = window.CommentLayerLocal({ endpoint: cfg.endpoint });
    }
    await store.ready;
    if (cfgKey !== key) { if (store.close) store.close(); return; }
    if (cl) { cl.destroy(); cl = null; subs.length = 0; }   // друга лінія: інстанс завжди ОДИН
    iterNum = cfg.version;
    cl = window.CommentLayer.create().init({
      projectId: cfg.module ? cfg.channel : cfg.project, storage: store, version: cfg.version, local: cfg.ch === "local",
      anchors: provider, audiences: env.audiences(), onAudience: env.onAudience,
      // особа машини — запасне імʼя автора, коли браузер не показує діалог імені (вбудований)
      defaultUser: cfg.user || null,
    });
    tick();
  }
  const fail = (e) => env.fail(e);

  return {
    /** Вхід у «Огляд». */
    enter() {
      const back = !active;   // саме ПОВЕРНЕННЯ в «Огляд», а не кожен render() у ньому (NEW-4)
      active = true; measure();
      // Інстанс уже є під цей канал — перечитати: живий вид міг лишити/видалити
      // піни, а локальний адаптер сам не опитує (ревʼю T-45, D2).
      const had = back && cl && cfgKey === keyNow();
      ensure().catch(fail);
      if (had && cl.store && typeof cl.store.refresh === "function") {
        Promise.resolve(cl.store.refresh()).catch(() => { /* мережа — наступного разу */ });
      }
      tick();
    },
    /** Вихід у живий вид: шар ховається разом із полотном (`#canvas[hidden]`). */
    // Режим коментування не переживає виходу з «Огляду»: у живому виді свій коментатор.
    leave() { active = false; if (cl && cl.commentMode) cl.setCommentMode(false); },
    /** Полотно перебудоване (кадри, розкладка, канал, ітерація). */
    rebuild() { if (!active) return; measure(); ensure().catch(fail); tick(); },
    /** Кадр камери. */
    tick,
    /** Для тестів і діагностики: живий інстанс коментатора. */
    get layer() { return cl; },
  };
}
