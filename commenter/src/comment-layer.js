/*!
 * comment-layer — drop-in Figma-style comments for AI-generated web UIs.
 * A comment is a change request; when its region is regenerated it auto-resolves.
 *
 * Usage:
 *   <script src="comment-layer.js"></script>
 *   <script>
 *     CommentLayer.init({ projectId: 'my-app' });   // localStorage by default
 *     // after your AI rewrites the UI:
 *     CommentLayer.regenerated();
 *   </script>
 *
 * Everything lives in a Shadow DOM so host styles never collide with the widget.
 * No build step, no framework assumptions.
 */
import { buildContextBundle, iterationOf } from './context-bundle.js';
import { audiencesHTML, notifyAudience } from './audiences.js';
import { fingerprint, findMatch, classify, MATCH_THRESHOLD } from './anchor.js';

(function (global) {
  'use strict';

  // Алгоритм якоря — у ./anchor.js (T-45): один на віджет, затвор і «Огляд».
  /* ===========================================================================
   * 2. Storage adapters. Default = localStorage (zero-config). Pass your own
   *    (e.g. the Supabase adapter) via init({ storage: adapter }).
   *    Adapter contract:  load(): Comment[]   save(comments): void
   * ========================================================================= */
  function LocalStorageAdapter(projectId) {
    const key = 'comment-layer:' + projectId;
    return {
      load() { try { return JSON.parse(localStorage.getItem(key) || '[]'); } catch { return []; } },
      save(comments) { localStorage.setItem(key, JSON.stringify(comments)); },
    };
  }

  /* ===========================================================================
   * 3. Identity (lightweight — a name, stored locally). Real auth is a later
   *    concern handled by the Supabase adapter.
   * ========================================================================= */
  /* Імʼя автора: явне (`opts.user`) → уже введене на цьому походженні
     (localStorage) → запасне від хоста (`opts.defaultUser`, T-45: оболонка
     канваса знає особу машини) → `prompt()` → «Anonymous».
     ⛔ `prompt()` лише ПІД ОХОРОНОЮ і лише останнім: браузер уміє його вимкнути —
     Chrome після «не показувати діалоги» мовчки віддає null, а вбудований
     браузер Electron КИДАЄ «prompt() is not supported». До T-45 цей виняток
     обривав збереження коментаря в обох режимах, і кнопка «Comment» не робила
     нічого (живий огляд власника 29.09.2026). Канонічне пояснення про діалоги —
     `design-canvas/app/ask.js`. */
  function getUser(preset, fallback) {
    if (preset && preset.name) return preset;
    let name = null;
    try { name = localStorage.getItem('comment-layer:user'); } catch (e) { name = null; }
    if (!name && fallback && fallback.name) name = String(fallback.name).trim();
    if (!name) {
      try { name = (prompt('Your name (for comments):', '') || '').trim(); } catch (e) { name = ''; }
      name = name || 'Anonymous';
    }
    try { localStorage.setItem('comment-layer:user', name); } catch (e) { /* приватне вікно — імʼя на сесію */ }
    return { name };
  }

  /* ===========================================================================
   * 4. The widget (Shadow DOM). Pins overlay the host page; a side panel lists
   *    open comments and history.
   * ========================================================================= */
  // Thin-line inline SVG icons (no external font/CDN). icon(name, size) → markup string.
  const ICONS = {
    search: '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
    x: '<path d="M6 6l12 12M18 6L6 18"/>',
    eye: '<path d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12z"/><circle cx="12" cy="12" r="2.6"/>',
    eyeOff: '<path d="M3 3l18 18"/><path d="M10.6 6.15A10.8 10.8 0 0112 6c6.4 0 10 6 10 6a17.6 17.6 0 01-3.4 3.95M6.5 6.55A17.4 17.4 0 002 12s3.6 6.5 10 6.5a10.7 10.7 0 004.2-.85"/>',
    sort: '<path d="M7 4v14M4 15l3 3 3-3M17 20V6M14 9l3-3 3 3"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7.5V12l3 2"/>',
    edit: '<path d="M4 20h4L19 9l-4-4L4 16v4z"/><path d="M14 5l4 4"/>',
    check: '<path d="M4 12.5l5 5L20 6"/>',
    trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>',
    reopen: '<path d="M4 12a8 8 0 108-8 8 8 0 00-6.6 3.5M4 4v3.5h3.5"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    comment: '<path d="M21 12a8 8 0 01-11.5 7.2L4 20l1.2-4.3A8 8 0 1121 12z"/>',
    element: '<rect x="4.5" y="4.5" width="15" height="15" rx="3.5"/>',
    text: '<path d="M5 6h14M12 6v12M9 19h6"/>',
    multi: '<path d="M12 3l9 5-9 5-9-5 9-5z"/><path d="M3 13l9 5 9-5"/>',
    area: '<path d="M4 8V4h4M20 8V4h-4M4 16v4h4M20 16v4h-4"/>',
    arrow: '<path d="M7 17L17 7M17 7H9M17 7v8"/>',
    freeze: '<path d="M12 2v20M4.5 6.5l15 11M19.5 6.5l-15 11"/><path d="M12 6.5l2.5-2M12 6.5L9.5 4.5M12 17.5l2.5 2M12 17.5l-2.5 2"/>',
    // For audience rows. Generic on purpose — a host picks one of these by
    // NAME; this widget must not learn what its channels mean.
    bot: '<path d="M12 8V4H8"/><rect x="4" y="8" width="16" height="12" rx="2"/>'
      + '<path d="M2 14h2M20 14h2M15 13v2M9 13v2"/>',
    team: '<path d="M16 21v-2a4 4 0 00-4-4H6a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/>'
      + '<path d="M22 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/>',
  };
  /**
   * Підпис ширини, на якій поставлено пін.
   *
   * Коментар «цей список має бути вертикально» був прочитаний як вимога на ВСІХ
   * ширинах, хоча дизайнер дивився мобільну версію — раунд правок пішов не туди
   * (03.09.2026). Дані були тут від початку: `meta.viewport` пишеться при
   * створенні піна. Бракувало виводу.
   *
   * ⚠️ Межі 768/1024 — ТІ САМІ, що в `bin/inbox.py` на боці пайплайну.
   * Розійдуться — і той самий пін читатиметься як «планшет» в одному місці й
   * «мобільна» в іншому; це гірше за відсутність підпису.
   */
  /**
   * ДЕ на сторінці стоїть пін — словами (fb-06102026-c38f46).
   *
   * У SPA елемента піна часто немає в DOM: він на іншому кроці `@switch`, в
   * закритому оверлеї чи іншій вкладці. Повернути той стан ми не можемо (він
   * живе в застосунку, не в URL), тож хоча б кажемо, де шукати: найближчий
   * видимий заголовок над елементом і активний крок/вкладку (`aria-current`,
   * `aria-selected`, `aria-pressed`) у мить створення піна.
   */
  /* `opts.heading === false` — без заголовка: проєктні піни їдуть у Supabase, а ПІБ
     у заголовку («Картка клієнта: …») надійно не розпізнати (TD-36). */
  function captureContext(el, root, opts) {
    const withHeading = !(opts && opts.heading === false);
    const clip = (t) => String(t || '').replace(/\s+/g, ' ').trim().slice(0, 60);
    const shown = (n) => n.getClientRects().length > 0;
    /* ⛔ PII (ревʼю 1.51): контекст проєктних пінів їде в Supabase. Довга цифрова
       серія — це ЄДРПОУ, ІПН, номер справи, а не «де я»: такий текст не беремо. */
    const clean = (t) => t && !/\d{6,}/.test(t.replace(/[\s-]/g, ''));
    let heading = '';
    for (const h of root.querySelectorAll('h1,h2,h3,h4,[role="heading"]')) {
      if (h !== el && !h.contains(el)
          && !(h.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING)) continue;
      const t = clip(h.textContent);
      if (withHeading && shown(h) && clean(t)) heading = t;   // останній чистий перед елементом
    }
    const active = [];
    for (const a of root.querySelectorAll('[aria-current]:not([aria-current="false"]),[aria-selected="true"],[aria-pressed="true"]')) {
      /* Крок/вкладка — коротка мітка. Вибраний РЯДОК таблиці чи списку — це дані
         (ПІБ, назва компанії), а не навігація: їх пропускаємо. */
      if (a.closest('tr,[role="row"],[role="gridcell"],[role="option"]')) continue;
      const t = clip(a.textContent);
      if (t.length > 30 || !clean(t)) continue;
      if (t && shown(a) && !active.includes(t) && t !== heading) active.push(t);
      if (active.length === 2) break;
    }
    return heading || active.length ? { heading, active } : null;
  }

  /** Рядок для картки з `meta.ctx`: «Крок 2» · розділ «Ваш партнер». */
  function ctxLine(ctx) {
    if (!ctx || typeof ctx !== 'object') return '';
    const parts = (Array.isArray(ctx.active) ? ctx.active : []).map((a) => `«${a}»`);
    if (ctx.heading) parts.push(`розділ «${ctx.heading}»`);
    return parts.join(' · ');
  }

  // Is `a` a text-entry field the user is typing into right now?
  function isTypingField(a) {
    if (!a || a.nodeType !== 1) return false;
    const tag = (a.tagName || '').toLowerCase();
    const isField = tag === 'textarea' || tag === 'select' || a.isContentEditable
      || (tag === 'input' && !/^(checkbox|radio|button|submit|reset|file|range|color|image)$/i.test(a.type || 'text'));
    if (!isField) return false;
    // Canvas and diagram editors park focus in an off-screen 1px field to capture
    // keys. That is not typing, and it must not disable the shortcuts.
    const w = a.ownerDocument.defaultView || window;
    const r = a.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return false;
    if (r.bottom <= 0 || r.right <= 0 || r.top >= w.innerHeight || r.left >= w.innerWidth) return false;
    const st = w.getComputedStyle(a);
    return st.visibility !== 'hidden' && st.opacity !== '0';
  }
  // Where a key event really came from (may live in another, ancestor document).
  function keyOrigin(e) {
    if (!e) return null;
    const p = typeof e.composedPath === 'function' ? e.composedPath() : null;
    return (p && p[0]) || e.target || null;
  }
  // Typing = the event's origin OR the focused element of our own document is a field.
  function typingIn(e, active) {
    return isTypingField(keyOrigin(e)) || isTypingField(active);
  }

  function vpBand(w) {
    const n = Number(w);
    if (!Number.isFinite(n) || !n) return '?';
    if (n < 768) return 'мобільна';
    if (n < 1024) return 'планшет';
    return 'десктоп';
  }

  function icon(n, s) {
    return '<svg class="ic" width="' + (s || 16) + '" height="' + (s || 16) + '" viewBox="0 0 24 24" fill="none" ' +
      'stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">' + (ICONS[n] || '') + '</svg>';
  }

  const STYLE = `
    :host{all:initial}
    *{box-sizing:border-box;font-family:"Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
    .root{position:fixed;inset:0;pointer-events:none;z-index:2147483000;
      --s1:#15181D;--s2:#1B1F26;--s3:#232830;--line:#2A2F38;--line2:#39414C;
      --hi:#F4F6F9;--mid:#A2A9B2;--lo:#6E7681;--white:#fff;--onwhite:#14171C;
      --open:#FBBC55;--openbg:rgba(251,188,85,.13);--ok:#6AD09D;--okbg:rgba(106,208,157,.13);
      --bad:#F37373;--badbg:rgba(243,115,115,.13);--r:12px;--rsm:8px;color:var(--hi)}
    .root svg{display:block}
    .pin{position:fixed;transform:translate(-50%,-50%);min-width:26px;height:26px;padding:0 6px;border-radius:9px;
      background:var(--onwhite);color:var(--white);font-weight:800;font-size:11.5px;font-variant-numeric:tabular-nums;
      display:grid;place-items:center;box-shadow:0 4px 14px rgba(0,0,0,.5),0 0 0 2px rgba(244,246,249,.92);
      pointer-events:auto;cursor:pointer;transition:transform .14s ease}
    .pin:hover{transform:translate(-50%,-50%) scale(1.12)}
    /* Режим «полотно» (T-45): позицію несе обгортка .cp (transform на кожен кадр
       камери, без transition), ховер лишається за самим .pin. */
    .cp{position:fixed;left:0;top:0;pointer-events:none}
    .root.canvas .cp .pin{position:static;pointer-events:auto}
    .root.canvas .pin.off{min-width:0;height:20px;padding:0 8px;border-radius:10px;font-size:11px;font-weight:700;
      background:var(--s1);color:var(--hi);box-shadow:0 0 0 1px var(--line2);transform:translate(0,-130%);white-space:nowrap}
    .root.canvas .pin.off:hover{transform:translate(0,-130%) scale(1.06)}
    .root.canvas .pin.cluster{min-width:30px;height:26px;padding:0 9px;border-radius:13px;
      background:var(--open);color:var(--onwhite);box-shadow:0 4px 14px rgba(0,0,0,.35),0 0 0 2px rgba(20,23,28,.85)}
    .clhov{position:fixed;left:0;top:0;display:none;pointer-events:none;border:2px solid #FBBC55;border-radius:3px;
      box-shadow:0 0 0 3px rgba(251,188,85,.22);box-sizing:border-box}
    .root.canvas .mode[data-mode="text"],.root.canvas .mode[data-mode="multi"],.root.canvas .mode[data-mode="area"],
    .root.canvas .mfreeze{display:none}
    .root.canvas .panel{top:var(--cl-top,0px);height:calc(100% - var(--cl-top,0px))}
    .root.canvas .panel,.root.canvas .compose{cursor:auto;user-select:text;-webkit-user-select:text}
    .root.local .pin{min-width:18px;height:18px;padding:0;background:#7C6CF0;box-shadow:0 4px 14px rgba(0,0,0,.5),0 0 0 2px rgba(124,108,240,.55)}
    .root.local .seq{display:none}
    .modes{position:fixed;left:50%;bottom:4px;transform:translateX(-50%);opacity:0;pointer-events:none;
      display:flex;gap:3px;align-items:center;background:var(--s1);border:1px solid var(--line2);border-radius:12px;padding:4px;
      z-index:2147483250;box-shadow:0 24px 60px rgba(0,0,0,.6);transition:opacity .2s ease,bottom .2s ease}
    .modes.shift{left:calc(50% - 186px)}
    .modes.show{opacity:1;bottom:20px;pointer-events:auto}
    .modes .mode{font:600 12px/1 inherit;border-radius:8px;padding:8px 12px;cursor:pointer;display:inline-flex;align-items:center;gap:7px;
      border:0;background:transparent;color:var(--mid);transition:background .12s,color .12s}
    .modes .mode svg{width:15px;height:15px}
    .modes .mode:hover{background:var(--s3);color:var(--hi)}
    .modes .mode.active{background:var(--white);color:var(--onwhite)}
    /* Freeze is a toggle, not one of the modes — separate it and give it its own
       on-state so it never reads as "the selected mode". */
    .modes .mfreeze{margin-left:3px;border-left:1px solid var(--line2);border-radius:0 8px 8px 0;padding-left:13px}
    .modes .mfreeze.on{color:var(--open)}
    .modes .mfreeze.on:hover{background:var(--openbg);color:var(--open)}
    .mcompose{position:fixed;right:20px;bottom:80px;width:300px;display:none;flex-direction:column;
      background:var(--s1);border:1px solid var(--line2);border-radius:var(--r);padding:12px;pointer-events:auto;
      z-index:2147483250;box-shadow:0 24px 60px rgba(0,0,0,.6);transition:right .2s ease}
    .mcompose.show{display:flex}
    .mcompose.shift{right:378px}
    .mchead{font-size:12px;color:var(--mid);margin-bottom:8px;display:flex;align-items:center;gap:6px}
    .mchead svg{width:14px;height:14px}
    .mchead b{color:var(--hi);font-variant-numeric:tabular-nums}
    .mcta{width:100%;height:70px;resize:none;background:var(--s2);color:var(--hi);border:1px solid var(--line);border-radius:var(--rsm);padding:9px 10px;font:14px/1.5 inherit;outline:none}
    .mcta::placeholder{color:var(--lo)}
    .mcta:focus{border-color:var(--line2)}
    .mcompose .row{display:flex;gap:8px;margin-top:10px;justify-content:flex-end}
    .mcompose .row button{font:600 13px/1 inherit;border-radius:var(--rsm);padding:9px 13px;cursor:pointer;border:1px solid var(--line2);background:transparent;color:var(--mid);display:inline-flex;align-items:center;gap:7px}
    .mcompose .row button:hover{background:var(--s3);color:var(--hi)}
    .mcompose .row button svg{width:14px;height:14px}
    .mcompose .row .primary{background:var(--white);border-color:var(--white);color:var(--onwhite)}
    .mcompose .row .primary:hover{background:#e7eaef}
    .clarea{position:fixed;border:2px dashed var(--open);background:var(--openbg);z-index:2147483000;pointer-events:none;border-radius:6px}
    .mtag{font-size:10.5px;font-weight:600;color:var(--mid);background:var(--s3);border:1px solid var(--line);border-radius:999px;padding:2px 8px;display:inline-flex;align-items:center;gap:4px}
    .mtag svg{width:12px;height:12px}
    .handle{position:fixed;right:0;top:50%;transform:translateY(-50%);z-index:2147483200;pointer-events:auto;cursor:pointer;
      display:flex;flex-direction:column;align-items:center;gap:9px;border:0;border-radius:16px 0 0 16px;
      background:var(--white);color:var(--onwhite);padding:16px 11px;
      box-shadow:-8px 0 28px rgba(0,0,0,.45);transition:right .2s ease,transform .2s ease,background .12s,padding .12s}
    .handle:hover{transform:translateY(-50%) translateX(-4px);padding-left:15px}
    .handle:active{transform:translateY(-50%) translateX(-1px)}
    .handle.shift{right:372px}
    .handle svg{width:18px;height:18px}
    .handle .hlabel{writing-mode:vertical-rl;transform:rotate(180deg);font:600 12px/1 inherit;letter-spacing:.03em}
    .handle.active{background:var(--open)}
    .handle.active:hover{background:#f6c877}
    .cbadge{display:inline-grid;place-items:center;min-width:18px;height:18px;padding:0 5px;
      border-radius:999px;background:var(--onwhite);color:var(--white);font-size:11px;font-weight:700;font-variant-numeric:tabular-nums}
    .handle.active .cbadge{background:rgba(20,23,28,.22);color:var(--onwhite)}
    .pins.hide{display:none}
    .panel{position:fixed;top:0;right:0;width:372px;height:100%;background:var(--s1);border-left:1px solid var(--line);
      pointer-events:auto;display:flex;flex-direction:column;transform:translateX(100%);transition:transform .2s ease;z-index:2147483150}
    .panel.show{transform:none}
    .head{padding:16px 14px 14px 18px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:10px}
    .head .ttl{font-size:15px;font-weight:600;letter-spacing:-.01em}
    .count{font-size:12px;font-weight:600;color:var(--mid);background:var(--s3);border-radius:999px;padding:2px 9px;font-variant-numeric:tabular-nums}
    .head .eye{margin-left:auto}
    .iconbtn{width:34px;height:34px;border-radius:9px;display:grid;place-items:center;cursor:pointer;background:transparent;border:1px solid transparent;color:var(--mid);transition:background .12s,color .12s;padding:0}
    .iconbtn:hover{background:var(--s3);color:var(--hi)}
    .iconbtn svg{width:17px;height:17px}
    .toolbar{display:flex;gap:8px;align-items:center;padding:12px 14px 4px}
    .searchwrap{flex:1;display:flex;align-items:center;gap:8px;background:var(--s2);border:1px solid var(--line);border-radius:var(--rsm);padding:0 10px;transition:border-color .12s}
    .searchwrap:focus-within{border-color:var(--line2)}
    .searchwrap .si{color:var(--lo);display:flex}
    .searchwrap .si svg{width:16px;height:16px}
    .search{flex:1;background:none;border:0;outline:none;color:var(--hi);font:14px inherit;padding:9px 0}
    .search::placeholder{color:var(--lo)}
    .searchx{background:none;border:0;color:var(--mid);cursor:pointer;padding:0 2px;display:flex}
    .searchx[hidden]{display:none}
    .searchx svg{width:15px;height:15px}
    .searchx:hover{color:var(--hi)}
    .sort{cursor:pointer;font:600 12px/1 inherit;white-space:nowrap;border:1px solid var(--line2);background:transparent;color:var(--mid);border-radius:var(--rsm);padding:9px 11px}
    .sort:hover{background:var(--s3);color:var(--hi)}
    .tabs{display:flex;gap:2px;background:var(--s2);border:1px solid var(--line);border-radius:10px;padding:3px;margin:12px 14px 6px}
    /* The OPTIONAL audience row sits right above the Open/Closed one and
       borrows its whole look; only the gap to the row below is its own. */
    /* Аудиторія — НЕ фільтр. До 02.09.2026 вона стояла рядком «.tabs» над
       «Open/Closed» і виглядала дослівно як він: дві однакові пари пілюль,
       і сказати, котра з них аудиторія, було неможливо (скріншот власника).
       Тепер вона в шапці, поруч із заголовком, і відрізняється трьома
       речами одразу: іншим місцем, іншим кольором активного стану
       («--open», власний акцент віджета, проти білого у фільтра) і
       АСИМЕТРІЄЮ — назву показує лише активна. Остання й робить стан
       «максимально очевидним»: у смузі завжди читається ім'я поточної
       аудиторії, а друга є голою іконкою, по якій клікають. */
    .head .auds{display:flex;gap:2px;background:var(--s3);border:1px solid var(--line);
      border-radius:999px;padding:2px;flex:none}
    /* 28px — не стиль, а підлога: правило проєкту «жодна ціль не менша за
       28px по короткій стороні». Власник просив «маленький такий перемикач»,
       і 28 лишає його малим (значкові кнопки шапки — 34, вкладки фільтра —
       32), але вже влучним. Разом із «padding:2px» і рамкою обгортки це дає
       рівно 34px — тобто рядок аудиторій стає однієї висоти зі значковими
       кнопками поруч, і шапка не розʼїжджається. */
    .head .aud{display:inline-flex;align-items:center;gap:5px;height:28px;min-width:28px;
      justify-content:center;padding:0 8px;
      border:0;border-radius:999px;background:transparent;color:var(--mid);cursor:pointer;
      font:600 11px/1 inherit;transition:background .12s,color .12s}
    .head .aud:hover{color:var(--hi)}
    .head .aud .ic{width:14px;height:14px;display:block;flex:none}
    .head .aud .aud-t{display:none}
    .head .aud.active{background:var(--open);color:var(--onwhite)}
    .head .aud.active .aud-t{display:inline}
    .tab{flex:1;cursor:pointer;font:600 12px/1 inherit;padding:8px 6px;border-radius:7px;border:0;background:transparent;color:var(--mid);transition:color .12s}
    .tab:hover{color:var(--hi)}
    .tab.active{background:var(--white);color:var(--onwhite);box-shadow:0 1px 2px rgba(0,0,0,.4)}
    .tab.active:hover{color:var(--onwhite)}
    .list{overflow:auto;padding:10px 14px 20px;flex:1}
    .sect{color:var(--lo);font-size:11px;text-transform:uppercase;letter-spacing:.08em;margin:8px 4px 4px}
    .empty{color:var(--mid);font-size:12.5px;line-height:1.5;padding:10px 4px}
    .cl-prev{margin-top:10px;border-top:1px solid var(--line)}
    .cl-prev>summary{cursor:pointer;list-style:none;padding:9px 4px;font-size:11.5px;font-weight:600;color:var(--mid);display:flex;align-items:center;gap:6px}
    .cl-prev>summary::-webkit-details-marker{display:none}
    .cl-prev>summary svg{width:13px;height:13px}
    .cl-prev-item{padding:8px;margin:4px 0;background:var(--s3);border:1px solid var(--line);border-radius:9px}
    .cl-prev-meta{font-size:10.5px;color:var(--mid);margin-bottom:4px}
    .cl-prev-text{font-size:12.5px;line-height:1.45;margin-bottom:8px;overflow:hidden;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical}
    .cl-carry{display:inline-flex;align-items:center;gap:5px;font-size:11.5px;padding:5px 10px}
    .cl-carry svg{width:13px;height:13px}
    .c{position:relative;border:1px solid var(--line);border-radius:var(--r);padding:12px 13px;margin-bottom:10px;background:var(--s2);
      cursor:pointer;transition:border-color .12s,background .12s,box-shadow .12s}
    .c:hover{border-color:var(--line2);background:#1e232b;box-shadow:0 0 0 1px rgba(255,255,255,.03)}
    .jump{display:inline-flex;align-items:center;justify-content:center;width:26px;height:26px;border-radius:7px;color:var(--lo);cursor:pointer;transition:background .12s,color .12s}
    .jump:hover{background:var(--s3);color:var(--hi)}
    .jump svg{width:15px;height:15px}
    [data-tip]{position:relative}
    [data-tip]::after{content:attr(data-tip);position:absolute;bottom:calc(100% + 7px);left:50%;transform:translateX(-50%) translateY(3px);
      background:#0B0D10;color:var(--hi);border:1px solid var(--line2);border-radius:7px;padding:5px 9px;font:600 11px/1.1 inherit;white-space:nowrap;
      opacity:0;pointer-events:none;transition:opacity .12s ease,transform .12s ease;z-index:2147483300;box-shadow:0 8px 22px rgba(0,0,0,.5)}
    [data-tip]:hover::after{opacity:1;transform:translateX(-50%) translateY(0)}
    .jump[data-tip]::after,.head [data-tip]::after{bottom:auto;top:calc(100% + 6px);left:auto;right:0;transform:translateY(-3px)}
    .jump[data-tip]:hover::after,.head [data-tip]:hover::after{transform:translateY(0)}
    .c .shot{display:block;margin-top:10px;max-width:100%;border:1px solid var(--line);border-radius:9px;cursor:zoom-in}
    .c .otherpage{display:inline-flex;align-items:center;gap:5px;margin-top:8px;font-size:11.5px;color:var(--open)}
    .c .otherpage svg{width:13px;height:13px}
    .c .offscreen{display:flex;align-items:flex-start;gap:6px;margin-top:8px;font-size:11.5px;line-height:1.4;color:var(--lo)}
    .c .offscreen svg{width:13px;height:13px;flex:none;margin-top:2px}
    .c .top{display:flex;align-items:center;gap:8px;margin-bottom:8px}
    .seq{min-width:22px;height:20px;padding:0 6px;border-radius:6px;background:var(--white);color:var(--onwhite);font:800 10.5px/1 inherit;display:grid;place-items:center;flex:none;font-variant-numeric:tabular-nums}
    .c .who{font-weight:600;font-size:13px;color:var(--hi)}
    .badge{margin-left:auto;font-size:11px;font-weight:600;padding:3px 9px;border-radius:999px;display:inline-flex;align-items:center;gap:5px}
    .badge .d{width:6px;height:6px;border-radius:50%}
    .badge.open{background:var(--openbg);color:var(--open)}
    .badge.open .d{background:var(--open)}
    .badge.resolved{background:var(--okbg);color:var(--ok)}
    .badge.resolved .d{background:var(--ok)}
    .c .body{font-size:13.5px;line-height:1.5;color:#dbe0e7}
    .c .meta{color:var(--lo);font-size:11.5px;margin-top:9px;font-variant-numeric:tabular-nums}
    .c .when{color:var(--lo);font-size:11.5px;margin-top:4px;display:flex;align-items:center;gap:5px}
    .c .vptag{color:var(--lo)}
    .c .when svg{width:12px;height:12px}
    .c .acts{display:flex;gap:6px;margin-top:11px}
    .c .acts button{width:30px;height:30px;border-radius:7px;cursor:pointer;border:1px solid transparent;background:transparent;color:var(--mid);display:grid;place-items:center;padding:0;transition:background .12s,border-color .12s,color .12s}
    .c .acts button svg{width:15px;height:15px}
    .c .acts button:hover{background:var(--s3);color:var(--hi)}
    .c .acts .ghost{border-color:var(--line2)}
    .c .acts .primary{background:var(--white);border-color:var(--white);color:var(--onwhite)}
    .c .acts .primary:hover{background:#e7eaef}
    .c .acts .danger:hover{background:var(--badbg);color:var(--bad);border-color:transparent}
    .csel{font-size:12.5px;line-height:1.45;color:var(--mid);border-left:2px solid var(--open);background:rgba(251,188,85,.08);border-radius:0 6px 6px 0;padding:6px 10px;font-style:italic}
    .c .csel{margin-top:8px}
    .compose .csel{margin-bottom:10px}
    .clmark{background:rgba(251,188,85,.32);color:var(--hi);border-radius:2px;padding:0 1px}
    .editform textarea.editta{width:100%;height:72px;resize:vertical;background:var(--s2);color:var(--hi);border:1px solid var(--line);border-radius:var(--rsm);padding:9px 10px;font:14px/1.5 inherit;margin-bottom:8px;outline:none}
    .editform textarea.editta:focus{border-color:var(--line2)}
    .c.hist{opacity:.72}
    .c.hist:hover{opacity:1}
    @keyframes cl-flash{0%{box-shadow:0 0 0 2px var(--white),0 0 20px rgba(255,255,255,.35);border-color:var(--white)}100%{box-shadow:none}}
    .c.flash{animation:cl-flash 1.3s ease}
    .compose{position:fixed;width:290px;background:var(--s1);border:1px solid var(--line2);border-radius:var(--r);padding:12px;
      box-shadow:0 24px 60px rgba(0,0,0,.6);pointer-events:auto;z-index:2147483100}
    .compose textarea{width:100%;height:70px;resize:none;background:var(--s2);color:var(--hi);border:1px solid var(--line);border-radius:var(--rsm);padding:9px 10px;font:14px/1.5 inherit;outline:none}
    .compose textarea::placeholder{color:var(--lo)}
    .compose textarea:focus{border-color:var(--line2)}
    .compose .row{display:flex;gap:8px;margin-top:10px;justify-content:flex-end}
    .compose button{font:600 13px/1 inherit;border-radius:var(--rsm);padding:9px 13px;cursor:pointer;border:1px solid var(--line2);background:transparent;color:var(--mid);display:inline-flex;align-items:center;gap:7px}
    .compose button:hover{background:var(--s3);color:var(--hi)}
    .compose button svg{width:14px;height:14px}
    .compose button.primary{background:var(--white);border-color:var(--white);color:var(--onwhite)}
    .compose button.primary:hover{background:#e7eaef}
    .cllb{position:fixed;inset:0;background:rgba(6,7,9,.86);z-index:2147483400;display:flex;align-items:center;justify-content:center;padding:32px;pointer-events:auto;cursor:zoom-out}
    .cllb img{max-width:92vw;max-height:92vh;border-radius:10px;border:1px solid var(--line2);box-shadow:0 30px 90px rgba(0,0,0,.7)}
    .pfoot{display:flex;align-items:center;gap:7px;padding:9px 14px;border-top:1px solid var(--line);font-size:11.5px;color:var(--lo);flex:none}
    .pfoot kbd{font:700 10px/1 inherit;background:var(--s2);border:1px solid var(--line2);border-bottom-width:2px;border-radius:5px;padding:3px 6px;color:var(--mid)}
    .pinpop{position:fixed;max-width:260px;background:var(--s1);border:1px solid var(--line2);border-radius:10px;padding:10px 12px;box-shadow:0 16px 44px rgba(0,0,0,.6);z-index:2147483260;pointer-events:none;opacity:0;transform:translateY(3px);transition:opacity .12s ease,transform .12s ease}
    .pinpop.show{opacity:1;transform:translateY(0)}
    .pinpop .pptop{display:flex;align-items:center;gap:8px;margin-bottom:6px}
    .pinpop .who{font-weight:600;font-size:13px;color:var(--hi)}
    .pinpop .ppbody{font-size:13px;line-height:1.45;color:#dbe0e7;display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden}

    /* Controls that only exist on touch / narrow screens are hidden by default. */
    .modes .mstop{display:none}
    .sheetpeek{display:none}
    .sheetgrab{display:none}
    .sheetscrim{display:none}

    /* ---- Mobile / narrow screens (≤640px) ----------------------------------
       One round comment FAB starts/stops commenting; the mode bar gains a
       second "Show comments" row that pulls the review panel up as a bottom
       sheet. Nothing else sits on the page. Desktop layout is untouched. */
    @media (max-width:640px){
      /* Review panel → bottom sheet (slides up from the bottom). */
      .panel{top:auto;bottom:0;left:0;right:0;width:100%;height:86vh;border-left:0;
        border-top:1px solid var(--line);border-radius:18px 18px 0 0;transform:translateY(100%);
        box-shadow:0 -18px 50px rgba(0,0,0,.55)}
      /* base .panel.show{transform:none} lands it fully open at the bottom */
      .pfoot{display:none}                              /* “C to comment” hint — no key on touch */

      .sheetgrab{display:block;flex:none;width:38px;height:4px;border-radius:999px;
        background:var(--line2);margin:9px auto 3px;cursor:pointer}

      /* Dim, tap-to-close scrim behind the open sheet (sits above the mode bar). */
      .sheetscrim{position:fixed;inset:0;background:rgba(6,7,9,.5);z-index:2147483255;
        opacity:0;pointer-events:none;transition:opacity .2s ease}
      .panelopen .sheetscrim{display:block;opacity:1;pointer-events:auto}
      .panel{z-index:2147483260}                        /* sheet above the scrim & mode bar */

      /* One round icon-only FAB: tap to start/stop commenting. */
      .handle{top:auto;bottom:calc(18px + env(safe-area-inset-bottom));right:16px;transform:none;
        width:56px;height:56px;padding:0;gap:0;justify-content:center;border-radius:999px;
        box-shadow:0 10px 28px rgba(0,0,0,.5)}
      .handle:hover{transform:none;padding:0}
      .handle:active{transform:scale(.94)}
      .handle.shift{right:16px}                         /* ignore desktop side-shift */
      .handle svg{width:23px;height:23px}
      .handle .hlabel{display:none}                     /* icon-only on mobile */
      .handle .cbadge{position:absolute;top:-4px;right:-4px}

      .arming .handle{display:none}                     /* while commenting, the mode bar takes over */
      .panelopen .handle{opacity:0;pointer-events:none}

      .modes{left:12px;right:12px;transform:none;bottom:calc(12px + env(safe-area-inset-bottom));
        flex-wrap:wrap}                                  /* modes on row 1, "Show comments" on row 2 */
      .modes.show{bottom:calc(12px + env(safe-area-inset-bottom))}
      .modes.shift{left:12px}
      .modes .mode{flex:1;justify-content:center;padding:12px 6px;font-size:12.5px}
      .modes .mode[data-mode="area"]{display:none}      /* drag-select doesn't map to touch */
      .modes .mstop{display:inline-flex;flex:0 0 auto}

      /* Second row of the mode bar: Freeze toggle + "Show comments" (pulls up the
         review sheet). Modes and Done stay on row 1. */
      .sheetpeek{display:inline-flex;align-items:center;justify-content:center;gap:7px;
        flex:1 1 55%;margin-top:4px;padding:11px 6px;cursor:pointer;
        border:0;border-top:1px solid var(--line);background:transparent;color:var(--mid);
        font:600 12.5px/1 inherit;border-radius:0 0 9px 0;transition:background .12s,color .12s}
      .sheetpeek:hover{background:var(--s3);color:var(--hi)}
      .sheetpeek svg{width:15px;height:15px}
      .modes .mfreeze{flex:1 1 35%;margin:4px 0 0;padding:11px 6px;
        border:0;border-top:1px solid var(--line);border-radius:0 0 0 9px}

      /* Composers dock above the (now two-row) mode bar, so their action
         buttons never hide behind it. */
      .mcompose{left:12px;right:12px;width:auto;bottom:calc(126px + env(safe-area-inset-bottom))}
      .mcompose.shift{right:12px}
      .mcta{font-size:16px}                             /* ≥16px avoids iOS auto-zoom */

      .compose{left:12px !important;right:12px !important;width:auto !important;
        top:auto !important;bottom:calc(126px + env(safe-area-inset-bottom)) !important}
      .compose textarea{font-size:16px}

      .search{font-size:16px}
      .pin{min-width:30px;height:30px}                  /* larger tap target */
    }
    .root.hosted .handle,.root.hosted .panel,.root.hosted .sheetscrim,.root.hosted .sheetpeek{display:none !important}
  `;

  /* ===========================================================================
   * 5. Controller
   * ========================================================================= */
  const CommentLayer = {
    version: '1.3.0',   // bump on release; exposed so hosts/self-hosters can check what they run
    _inited: false,
    /**
     * `opts.anchors` — режим «полотно» (T-45, Design Canvas «Огляд»). Без нього
     * поведінка рівно як до T-45: піни в DOM сторінки. З ним віджет живе в
     * документі оболонки і позицій у DOM не шукає — питає постачальника:
     *   mount: Element          куди покласти шар (прихований → шар прихований)
     *   active(): boolean       чи полотно зараз на екрані (клавіші лише тоді)
     *   place(comments)         → [{key, x, y, ids, cluster, vis}] екранні точки
     *   reveal(comment)         переліт камери до піна
     *   revealKey(key)          клік по кластеру
     *   subscribe(fn)           постачальник кличе fn() на кадр камери / зміну розкладки
     *   top(): number           (необовʼязково) верх полотна у вікні — нижче за смугу хоста
     *   hit(x, y)               (етап 2) ціль під курсором: {key, rect, fp, anchor, meta, …} | null
     *   armed(on)               (етап 2) режим коментування ввімкнено/вимкнено — хост гасить свій клік
     *   enrich(target)          (етап 2) → Promise<{fp, htmlSnapshot}|null>: повний відбиток і HTML
     *   shot(target)            (етап 2) → Promise<dataURL|null>: скриншот для картки
     * Межа та сама, що в Claude Design: полотно не знає про треди, віджет — про камеру.
     */
    init(opts = {}) {
      if (this._inited) return this;
      this.opts = opts;
      this.anchors = opts.anchors && typeof opts.anchors.place === 'function' ? opts.anchors : null;
      this.projectId = opts.projectId || 'default';
      this.target = (typeof opts.target === 'string' ? document.querySelector(opts.target) : opts.target) || document.body;
      this.store = opts.storage && typeof opts.storage === 'object' ? opts.storage : LocalStorageAdapter(this.projectId);
      this.user = opts.user || null;
      this.appVersion = opts.version != null ? opts.version : null;
      this.freeze = opts.freeze !== false;   // hold the host page still while commenting; opt out with freeze:false
      if (this.anchors) this.freeze = false;  // полотно — не сторінка: заморожувати нічого
      this.appLocal = !!opts.local;   // «Локальні · мені» — інший колір піна, без номера
      /* Режим хоста (Deai 0.26.0): ручку й власну панель тримає ОБОЛОНКА; коментатор малює піни, форму й рядок режимів
         і повідомляє хоста колбеками (`onReady`/`onChange`/`onSelect`/`onMode`). Без `host` — поведінка як до 0.26.0. */
      this._hostOpts = opts.host && typeof opts.host === 'object' ? opts.host : null;
      this.comments = this.store.load();
      this._backupKey = 'comment-layer:backup:' + this.projectId;
      this._recoverBackup();          // resurrect anything a failed write left behind
      this._backfillSeq();            // give legacy comments a stable number too
      // Monotonic display numbering: remember the highest seq ever issued (per project,
      // in localStorage) so deleting a comment never frees its number for reuse.
      this._seqHighKey = 'comment-layer:seqmax:' + this.projectId;
      this._seqHigh = this.comments.reduce((m, c) => Math.max(m, (c.meta && c.meta.seq) || 0), 0);
      try { this._seqHigh = Math.max(this._seqHigh, parseInt(localStorage.getItem(this._seqHighKey) || '0', 10) || 0); } catch (e) {}
      this.commentMode = false;
      this.pending = null;
      this._buildUI();
      this._relocate();
      this._render();
      if (opts.autoDetectRegeneration) this._watch();
      // Live updates: re-render when the backing store reports external changes
      // (e.g. another reviewer added a comment) — no page reload needed.
      if (this.store.subscribe) this.store.subscribe((comments) => this._onExternalChange(comments));
      if (this.anchors) {
        // Полотно рухає камера, а не скрол: постачальник кличе нас на кожен її кадр.
        this.anchors.subscribe(() => { if (!this._dead) this._placePins(); });
      } else {
        window.addEventListener('scroll', () => this._placePins(), true);
        window.addEventListener('resize', () => this._placePins());
      }
      this._inited = true;
      this._emit('onReady');
      this._emitChange();
      return this;
    },

    // Merge an authoritative set from the store with any local-only (unsynced)
    // comments, then re-render. Never drops a local comment the server lacks yet.
    _onExternalChange(external) {
      // Знищений інстанс (оболонка перемкнула канал): сховище відписати нічим —
      // Supabase-адаптер `unsubscribe` не має, — тому гасимо тут.
      if (this._dead || !Array.isArray(external)) return;
      const byId = new Map(external.map((c) => [c.id, c]));
      // Keep a local comment the server lacks ONLY if it's still unsynced (pending).
      // A synced comment now absent was deleted elsewhere → let it go (live delete).
      for (const local of this.comments) {
        if (!local._pending) continue;
        const ext = byId.get(local.id);
        if (!ext) byId.set(local.id, local);
        // Сховище може показати пін ОПТИМІСТИЧНО, до підтвердження запису
        // (локальний адаптер сповіщає одразу в save). Позначку не губимо: інакше
        // впалий запис лишає пін поза бекапом — тільки в памʼяті вікна (fb 05.11.2026).
        else ext._pending = true;
      }
      this.comments = [...byId.values()];
      this._seqHigh = this.comments.reduce((m, c) => Math.max(m, (c.meta && c.meta.seq) || 0), this._seqHigh || 0);
      this._relocate();
      this._render();
    },

    _buildUI() {
      const host = document.createElement('div');
      host.setAttribute('data-comment-layer', '');
      this._host = host;
      ((this.anchors && this.anchors.mount) || document.body).appendChild(host);
      const sh = host.attachShadow({ mode: 'open' });
      const style = document.createElement('style'); style.textContent = STYLE; sh.appendChild(style);
      const root = document.createElement('div'); root.className = 'root' + (this.appLocal ? ' local' : '') + (this.anchors ? ' canvas' : '') + (this._hostOpts ? ' hosted' : ''); sh.appendChild(root);
      root.innerHTML = `
        <div class="pins"></div>
        <div class="pinpop"></div>
        <div class="modes">
          <button class="mode active" data-mode="element" title="Comment on one element">${icon('element')}Element</button>
          <button class="mode" data-mode="text" title="Select text and comment on it">${icon('text')}Text</button>
          <button class="mode" data-mode="multi" title="Pick several elements for one comment">${icon('multi')}Multi</button>
          <button class="mode" data-mode="area" title="Drag a region to comment on">${icon('area')}Area</button>
          <button class="mode mstop" title="Stop commenting">${icon('x', 15)}Done</button>
          <button class="mode mfreeze" title="Freeze the page — keep dropdowns, modals and tooltips open while you comment">${icon('freeze', 15)}Freeze</button>
          <button class="sheetpeek" title="Open comments" aria-label="Open comments">${icon('comment', 15)}<span class="speektxt">Show comments</span></button>
        </div>
        <div class="mcompose">
          <div class="mchead">${icon('multi', 14)}Comment on <b class="mccount">0</b> element(s)</div>
          <textarea class="mcta" placeholder="Leave a change request…"></textarea>
          <div class="row"><button class="mccancel">Clear</button><button class="primary mcsave">${icon('check')}Comment</button></div>
        </div>
        <button class="handle" title="Comment — open the panel">
          <span class="hicon">${icon('comment', 18)}</span>
          <span class="hlabel lbl">Comment</span>
          <span class="cbadge" hidden></span>
        </button>
        <div class="sheetscrim"></div>
        <div class="panel">
          <div class="sheetgrab" aria-hidden="true"></div>
          <div class="head">
            <span class="ttl">Comments</span><span class="count">0</span>
            ${audiencesHTML(this.opts.audiences, icon)}
            <button class="eye iconbtn" data-tip="Hide pins" aria-label="Hide pins">${icon('eyeOff')}</button>
            <button class="x iconbtn" data-tip="Close panel" aria-label="Close panel">${icon('x')}</button>
          </div>
          <div class="toolbar">
            <div class="searchwrap"><span class="si">${icon('search')}</span><input class="search" type="text" placeholder="Search — text, author, #5, date…"><button class="searchx" hidden title="Clear">${icon('x', 15)}</button></div>
            <button class="sort" title="Sort by date">↓ Newest</button>
          </div>
          <div class="tabs"><button class="tab tabOpen active" data-tab="open">Open</button><button class="tab tabClosed" data-tab="resolved">Closed</button></div>
          <div class="list"></div>
          <div class="pfoot"><kbd>C</kbd> to comment</div>
        </div>`;
      this._sh = root;
      this._pins = root.querySelector('.pins');
      this._pinpop = root.querySelector('.pinpop');
      this._panel = root.querySelector('.panel');
      this._list = root.querySelector('.list');
      this._fab = root.querySelector('.handle');       // right-edge pull tab (opens panel + arms commenting)
      this._toggleBtn = this._fab;
      this._cbadge = root.querySelector('.cbadge');
      // `.hlabel`, не `.lbl`: обидва класи висять на тому самому елементі
      // ручки, але `.lbl` — назва загальна, і будь-який новий підпис у
      // панелі міг би її позичити. Тоді цей пошук вертав би ЧУЖИЙ вузол
      // залежно від порядку розмітки, і «Comment»/«Stop» писалось би не
      // туди. `.hlabel` належить ручці одній.
      this._lbl = root.querySelector('.hlabel');
      this._total = root.querySelector('.count');
      this._tab = 'open';
      this._tabOpen = root.querySelector('.tabOpen');
      this._tabClosed = root.querySelector('.tabClosed');
      root.querySelectorAll('.tab[data-tab]').forEach((t) => {
        t.onclick = () => { this._tab = t.getAttribute('data-tab'); this._render(); };
      });
      /* Audience row — optional, see src/audiences.js. Wired by `data-aud`, and
         the Open/Closed sweep above is narrowed to `[data-tab]`: the two rows
         share a look, they must not share a handler. A plain `.tab` sweep would
         have made every audience click also set `this._tab` to `null` and reset
         the open/closed filter.
         The click only REPORTS — no re-render, no state kept here. Whatever the
         host does with the choice (Design Canvas reloads the frame in the other
         channel) rebuilds this panel from scratch, so `active` comes back from
         the host's own truth instead of a copy we would have to keep in step. */
      root.querySelectorAll('[data-aud]').forEach((b) => {
        b.onclick = () => notifyAudience(this.opts.onAudience, b.getAttribute('data-aud'));
      });
      // Search + sort toolbar.
      this._query = '';
      this._sort = 'new'; // 'new' = newest first (by seq), 'old' = oldest first
      const search = root.querySelector('.search');
      const searchx = root.querySelector('.searchx');
      search.oninput = () => { this._query = search.value.trim().toLowerCase(); searchx.hidden = !search.value; this._render(); };
      searchx.onclick = () => { search.value = ''; this._query = ''; searchx.hidden = true; this._render(); search.focus(); };
      this._sortBtn = root.querySelector('.sort');
      this._sortBtn.onclick = () => {
        // cycle: newest → oldest → recently closed
        const was = this._sort;
        this._sort = this._sort === 'new' ? 'old' : this._sort === 'old' ? 'closed' : 'new';
        this._sortBtn.textContent = this._sort === 'new' ? '↓ Newest' : this._sort === 'old' ? '↑ Oldest' : '↺ Recent';
        // "recently closed" applies to the Closed list — show it, then put the tab
        // back where it was once the cycle moves off 'closed'.
        if (this._sort === 'closed') { this._tabWas = this._tab; this._tab = 'resolved'; }
        else if (was === 'closed') { this._tab = this._tabWas || 'open'; this._tabWas = null; }
        this._render();
      };
      this._pinsHidden = false;
      this._eye = root.querySelector('.eye');
      this._eye.onclick = () => this._togglePins();

      // Annotation modes: element (default) | text | multi | area, + animation pause.
      this._mode = 'element';
      this._multiSel = [];
      this._modesBar = root.querySelector('.modes');
      this._mcompose = root.querySelector('.mcompose');
      this._mcta = root.querySelector('.mcta');
      this._mccount = root.querySelector('.mccount');
      root.querySelectorAll('.mode:not(.mstop):not(.mfreeze)').forEach((b) => {
        b.onclick = () => {
          this._clearMulti(); this._clearArea(); this._setHover(false); // drop any element outline
          this._mode = b.getAttribute('data-mode');
          root.querySelectorAll('.mode:not(.mstop):not(.mfreeze)').forEach((x) => x.classList.toggle('active', x === b));
          this._mcompose.classList.toggle('show', this._mode === 'multi'); // multi uses a modal
          this._armComment(true); // picking a mode readies commenting
        };
      });
      // Mobile mode bar carries a "Done" button (the pull-tab is hidden while commenting).
      root.querySelector('.mstop').onclick = () => this._armComment(false);
      // Freeze toggle — shields the host page from the events that dismiss its own
      // overlays (see _shield). On by default; turn it off to operate the host UI.
      this._freezeBtn = root.querySelector('.mfreeze');
      this._freezeBtn.onclick = () => this._setFreeze(!this.freeze);
      this._setFreeze(this.freeze);   // reflect the initial state on the toggle
      root.querySelector('.mcsave').onclick = () => this._finishMulti();
      root.querySelector('.mccancel').onclick = () => this._clearMulti();
      this._mcta.onkeydown = (e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); this._finishMulti(); } };
      // The pull tab toggles comment mode. Turning it ON also opens the panel (for
      // context); comment mode and the panel are otherwise independent — closing the
      // panel does NOT stop commenting.
      this._toggleBtn.onclick = () => this._toggleComment();
      // Mobile bottom-sheet controls: the drawer tab opens the panel; the scrim and
      // the grabber close it. (No-ops on desktop, where these are display:none.)
      this._speektxt = root.querySelector('.speektxt');
      root.querySelector('.sheetpeek').onclick = () => this._openPanel();
      root.querySelector('.sheetscrim').onclick = () => this._closePanel();
      root.querySelector('.sheetgrab').onclick = () => this._closePanel();
      root.querySelector('.x').onclick = () => this._closePanel();

      // Delegated actions on comment cards (resolve / reopen / delete),
      // and clicking the card body focuses + flashes its element on the page.
      this._editingId = null;
      this._list.addEventListener('click', (e) => {
        const btn = e.target.closest('[data-cl-act]');
        if (btn) {
          const id = btn.getAttribute('data-cl-id');
          const act = btn.getAttribute('data-cl-act');
          if (act === 'resolve') this.resolveComment(id);
          else if (act === 'reopen') this.reopenComment(id);
          else if (act === 'delete') this.removeComment(id);
          else if (act === 'carry') this._carryToCurrent(id);
          else if (act === 'edit') { this._editingId = id; this._render(); }
          else if (act === 'edit-cancel') { this._editingId = null; this._render(); }
          else if (act === 'edit-save') {
            const ta = btn.closest('.c').querySelector('.editta');
            const v = ta && ta.value.trim();
            const c = this.comments.find((x) => x.id === id);
            if (c && v) { c.text = v; c._pending = true; }
            this._editingId = null; this._persist(); this._render();
          }
          return;
        }
        // Click a card's screenshot → open it full-screen (lightbox), not navigate.
        const img = e.target.closest('img.shot');
        if (img) { e.stopPropagation(); this._openLightbox(img.getAttribute('src')); return; }
        // Don't navigate while typing in an editor; ignore clicks inside edit forms.
        if (this._editingId || e.target.closest('.editform')) return;
        const card = e.target.closest('.c');
        if (card && card.id) this._focusElement(card.id.slice(1)); // 'c<id>' → <id>
      });

      // capture clicks on the host page while in comment mode (stays armed so
      // you can drop several comments in a row until you click Stop / close)
      this._clickHandler = (e) => {
        if (!this.commentMode) return;
        if (this._host.contains(e.target)) return; // ignore widget chrome
        if (this.anchors) { this._canvasClick(e); return; }
        const el = e.target;
        if (!this.target.contains(el)) return;
        e.preventDefault(); e.stopPropagation();
        if (this._mode === 'multi') { this._toggleMulti(el); return; }
        if (this._mode === 'area' || this._mode === 'text') return; // handled by drag / mouseup
        const sel = (this._lastSel && el.textContent && el.textContent.includes(this._lastSel)) ? this._lastSel : '';
        this._openCompose(el, sel, sel ? { mode: 'text' } : null);
        this._lastSel = '';
      };
      document.addEventListener('click', this._clickHandler, true);

      // Text mode: a selection finishes on mouseup.
      this._upHandler = (e) => {
        if (!this.commentMode || this._mode !== 'text' || this._host.contains(e.target)) return;
        const s = window.getSelection && window.getSelection();
        const txt = s && s.toString().trim();
        if (!txt) return;
        const anchor = (s.anchorNode && s.anchorNode.nodeType === 3 ? s.anchorNode.parentElement : s.anchorNode) || e.target;
        if (!this.target.contains(anchor)) return;
        this._openCompose(anchor, txt, { mode: 'text' });
      };
      document.addEventListener('mouseup', this._upHandler, true);

      // Area mode: drag a rectangle → comment on the region.
      this._area = null; this._areaBox = null;
      this._areaDown = (e) => {
        if (!this.commentMode || this._mode !== 'area' || this._host.contains(e.target) || !this.target.contains(e.target)) return;
        e.preventDefault();
        this._area = { x0: e.clientX, y0: e.clientY };
        this._areaBox = document.createElement('div'); this._areaBox.className = 'clarea';
        this._pins.appendChild(this._areaBox);
      };
      this._areaMove = (e) => {
        if (!this._area || !this._areaBox) return;
        const x = Math.min(e.clientX, this._area.x0), y = Math.min(e.clientY, this._area.y0);
        const w = Math.abs(e.clientX - this._area.x0), h = Math.abs(e.clientY - this._area.y0);
        Object.assign(this._areaBox.style, { left: x + 'px', top: y + 'px', width: w + 'px', height: h + 'px' });
      };
      this._areaUp = (e) => {
        if (!this._area) return;
        const x = Math.min(e.clientX, this._area.x0), y = Math.min(e.clientY, this._area.y0);
        const w = Math.abs(e.clientX - this._area.x0), h = Math.abs(e.clientY - this._area.y0);
        this._clearArea();
        if (w < 8 || h < 8) return; // ignore stray clicks
        const el = this._elementAt(x + w / 2, y + h / 2);
        if (el) this._openCompose(el, '', { mode: 'area', rect: { x, y, w, h } });
      };
      document.addEventListener('mousedown', this._areaDown, true);
      document.addEventListener('mousemove', this._areaMove, true);
      document.addEventListener('mouseup', this._areaUp, true);

      // lightweight hover highlight in comment mode
      this._hoverEl = null;
      this._moveHandler = (e) => {
        if (!this.commentMode) return;
        if (this.anchors) { this._canvasHover(e); return; }
        if (this._hoverEl) { this._hoverEl.classList.remove('cl-hl'); this._hoverEl = null; }
        // Only outline elements when you're actually picking elements. In text /
        // area modes the outline is confusing (you're selecting text / a region).
        if (this._mode !== 'element' && this._mode !== 'multi') return;
        const el = e.target;
        if (el && this.target.contains(el) && !this._host.contains(el)) { el.classList.add('cl-hl'); this._hoverEl = el; }
      };
      document.addEventListener('mousemove', this._moveHandler, true);
      /* Полотно: після панорами браузер однаково шле `click` (натиснули й
         відпустили над тим самим полотном). Без цієї мітки кожне перетягування
         в режимі коментування відкривало б композер у точці, де відпустили. */
      this._downHandler = (e) => { this._downAt = { x: e.clientX, y: e.clientY }; };
      if (this.anchors) document.addEventListener('pointerdown', this._downHandler, true);

      // Remember the last non-empty text selection so a click can turn it into a
      // text-range comment (the click itself usually collapses the selection).
      this._lastSel = '';
      this._selHandler = () => {
        const s = window.getSelection && window.getSelection();
        const t = s && s.toString().trim();
        if (t) this._lastSel = t;
      };
      document.addEventListener('selectionchange', this._selHandler);

      // Keyboard shortcuts: C = comment mode, P = panel, H = hide pins, Esc = cancel/close.
      this._keyHandler = (e) => {
        /* Режим «полотно»: клавіші — лише коли полотно на екрані. DOM-режим:
           рамка, у якій ми живемо, прихована (оболонка показує «Огляд») —
           клавіші не наші. Без цього прихований живий iframe ловив C/P/H на
           вікні оболонки (ми вішаємось на всі same-origin предки нижче) і
           відкривав свою невидиму панель поверх полотна. */
        if (this.anchors ? !this.anchors.active() : hiddenFrame()) return;
        /* Хост: клавіші з полів ХОСТА (пошук, редагування в його панелі — поза нашим shadow root) — його, не наші:
           інакше Esc у його полі виходив би з режиму коментування. Своя форма/редагування лишаються за шарованим Escape. */
        if (this._hostOpts) { const o = keyOrigin(e); if (isTypingField(o) && !(this._sh && this._sh.contains(o))) return; }
        const eaten = () => { e.preventDefault(); e.stopImmediatePropagation(); }; // ours — the host must not also act on it
        if (e.key === 'Escape') {
          const lb = this._sh.querySelector('.cllb');
          if (lb) { lb.remove(); eaten(); return; }
          const compose = this._sh.querySelector('.compose');
          if (compose) { compose.remove(); eaten(); return; }
          if (this._editingId) { this._editingId = null; this._render(); eaten(); return; }
          // Peel back one layer at a time: leave comment mode first (also clears any
          // multi/area selection — _armComment(false) does that), THEN close the panel.
          // Works with the panel closed too, since comment mode is panel-independent.
          // While frozen we swallow Escape either way, so the host's own modal survives.
          if (this.commentMode) { const f = this._frozen(); this._armComment(false); if (f) eaten(); return; }
          if (this._panel.classList.contains('show')) { this._closePanel(); eaten(); }
          return;
        }
        if (this._hostOpts) return;   // C/P/H — клавіші хоста
        if (this._isTyping(e) || e.metaKey || e.ctrlKey || e.altKey) return;
        const k = e.key.toLowerCase();
        if (k === 'c') { this._toggleComment(); eaten(); }
        else if (k === 'p') { this._panel.classList.contains('show') ? this._closePanel() : this._openPanel(); eaten(); }
        else if (k === 'h') { this._togglePins(); eaten(); }
      };
      // Bind on `window` (not `document`) in the capture phase: window capture runs
      // before any document- or target-level handler, so a host page that intercepts
      // keydown on document (or in the bubble phase) can't swallow the shortcut. This
      // is why `C` failed on some host apps.
      // Also bind on every same-origin ancestor window: review tools preview the page
      // inside an iframe, and keys go to whichever document holds focus — without this
      // the shortcut only works after clicking inside the frame.
      const keyTargets = [window];
      /* Хост сам тримає C/H на своєму вікні й на вікні рамки: предків коментатор не чіпає. */
      if (!this._hostOpts) {
        try {
          let w = window;
          while (w !== w.parent) { w = w.parent; void w.document.documentElement; keyTargets.push(w); }
        } catch (err) { /* cross-origin ancestor — can't listen there, ignore */ }
      }
      keyTargets.forEach((w) => w.addEventListener('keydown', this._keyHandler, true));
      this._keyTargets = keyTargets;   // для destroy()
      if (!this.anchors) this._installShield();   // щит — про сторінку-хоста, на полотні його нема від чого ставити

      // host-page styles (light DOM): hover highlight + page shift when panel open
      const hl = document.createElement('style');
      hl.textContent = '.cl-hl{outline:2px solid #FBBC55 !important;outline-offset:2px;cursor:crosshair !important}'
        + '.cl-msel{outline:2px solid #FBBC55 !important;outline-offset:2px;box-shadow:0 0 0 4px rgba(251,188,85,.22) !important}'
        + 'body.cl-shift{margin-right:372px !important;transition:margin-right .2s ease}'
        + '@keyframes cl-el-flash{0%{outline:3px solid #FBBC55;outline-offset:2px;box-shadow:0 0 0 4px rgba(251,188,85,.4)}100%{outline:3px solid transparent;box-shadow:none}}'
        + '.cl-el-flash{animation:cl-el-flash 1.5s ease}'
        // Frozen: hold the host page still so carousels / auto-dismissing toasts don't
        // run away mid-comment. Light-DOM selector only — our own UI lives in a shadow
        // root and keeps animating.
        + 'html.cl-freeze *,html.cl-freeze *::before,html.cl-freeze *::after{animation-play-state:paused !important}';
      document.head.appendChild(hl);
      this._hlStyle = hl;   // destroy() прибирає: інакше кожен інстанс полотна лишав свій <style>
    },

    // Panel open/close also shifts the host page (margin) so the panel sits
    // beside content instead of covering it, and moves the FAB clear of the panel.
    _openPanel() {
      if (this._hostOpts) return;   // панель — оболонки
      this._panel.classList.add('show');
      this._sh.classList.add('panelopen'); // mobile: full-screen overlay → hide the floating controls behind it
      // On mobile the panel is a full-screen overlay, so the page must NOT be pushed
      // aside (that would shove content off a phone screen). Only shift on desktop.
      if (!this._isMobile()) {
        if (!this.anchors) document.body.classList.add('cl-shift');   // полотно: панель ПОВЕРХ, зсув body зсунув би всю оболонку
        this._fab.classList.add('shift');
        if (this._mcompose) this._mcompose.classList.add('shift');
        if (this._modesBar) this._modesBar.classList.add('shift'); // center the bottom mode bar in the area left of the panel
      }
      setTimeout(() => this._placePins(), 220); // reflow finished → reposition pins
    },
    _closePanel() {
      this._panel.classList.remove('show');
      this._sh.classList.remove('panelopen');
      if (!this.anchors) document.body.classList.remove('cl-shift');
      this._fab.classList.remove('shift');
      if (this._mcompose) this._mcompose.classList.remove('shift'); // keep 'show': an armed multi-selection must stay saveable with the panel closed
      if (this._modesBar) this._modesBar.classList.remove('shift'); // mode bar re-centers on the full viewport
      // NOTE: closing the panel does NOT disarm — you can keep commenting with it closed.
      setTimeout(() => this._placePins(), 220);
    },
    // Narrow / touch layout: matches the CSS breakpoint so JS behavior stays in sync.
    _isMobile() { return typeof matchMedia === 'function' && matchMedia('(max-width:640px)').matches; },

    /* ---- freeze --------------------------------------------------------------
     * Host apps dismiss their own dropdowns / modals / tooltips on an outside
     * click, on focus loss and on pointer-out. Reaching for our Comment button
     * fires exactly those, so the overlay you wanted to comment on disappears
     * before you can. While frozen we keep those signals away from the host.
     * Note: an outside-click handler the host registered in the CAPTURE phase on
     * document still sees the click (it runs before the event reaches us), so the
     * reliable way to arm comment mode over an open overlay is the `C` key — it
     * produces no pointer event at all. Freeze covers everything else. */
    _frozen() { return !!(this.commentMode && this.freeze); },
    _setFreeze(on) {
      this.freeze = !!on;
      if (this._freezeBtn) {
        this._freezeBtn.classList.toggle('on', this.freeze);
        this._freezeBtn.setAttribute('aria-pressed', String(this.freeze));
      }
      this._syncFreeze();
    },
    _syncFreeze() { document.documentElement.classList.toggle('cl-freeze', this._frozen()); },
    _installShield() {
      const H = this._host;
      const inWidget = (e) => {
        const p = e.composedPath ? e.composedPath() : null;
        if (p && p.length) return p.indexOf(H) !== -1;
        const t = e.target;
        return t === H || !!(t && t.nodeType === 1 && H.contains(t));
      };
      // 1. Our own pointer events stop at the widget boundary, so the host's
      //    bubble-phase "clicked outside" handlers never learn about them.
      //    Gated on `freeze` alone, NOT on comment mode: the click that ARMS
      //    comment mode is the one that used to dismiss the overlay, and at that
      //    moment comment mode is still off. A click on our chrome is never a
      //    click "outside" from the host's point of view either way.
      const stopAtBoundary = (e) => { if (this.freeze) e.stopPropagation(); };
      ['pointerdown', 'pointerup', 'mousedown', 'mouseup', 'click', 'dblclick', 'contextmenu', 'touchstart', 'touchend']
        .forEach((t) => H.addEventListener(t, stopAtBoundary));
      // 2. Don't take focus off the host page: a control that never focuses can't
      //    trigger blur/focusout dismissal — and it keeps the shortcuts alive,
      //    since the typing guard looks at the focused element. Text fields inside
      //    the widget (compose, search) must still focus, so they're exempt.
      H.addEventListener('mousedown', (e) => {
        if (!this.freeze) return;              // same reason as (1): mousedown precedes arming
        const t = e.composedPath ? e.composedPath()[0] : e.target;
        const editable = t && t.nodeType === 1
          && (/^(input|textarea|select)$/i.test(t.tagName || '') || t.isContentEditable);
        if (!editable) e.preventDefault();     // suppress focus, keep the click
      }, true);
      // 3. Drop the dismiss-direction events coming from the host page before its
      //    handlers run. The "enter" counterparts pass through, so hovering still
      //    OPENS a tooltip — it just no longer closes while you comment on it.
      this._shield = (e) => {
        if (!this._frozen() || inWidget(e)) return;   // our own pin popovers must keep working
        e.stopImmediatePropagation();
      };
      ['mouseout', 'mouseleave', 'pointerout', 'pointerleave', 'focusout', 'blur']
        .forEach((t) => window.addEventListener(t, this._shield, true));
    },
    // `e` — the keydown event, when there is one. The focused element of OUR document is
    // not enough: the key handler is also bound on every same-origin ancestor window, and
    // when the user types into a field of that outer shell (task search, command palette)
    // our activeElement is just <body>. So the event's own origin counts too.
    _isTyping(e) {
      // The genuinely focused element, piercing shadow roots: clicking our chrome
      // makes document.activeElement the shadow HOST, which used to look like
      // "typing" and killed every shortcut until you clicked the page again.
      let a = document.activeElement;
      while (a && a.shadowRoot && a.shadowRoot.activeElement) a = a.shadowRoot.activeElement;
      return typingIn(e, a);
    },
    _armComment(on) {
      this.commentMode = on;
      if (this.anchors) {
        if (typeof this.anchors.armed === 'function') this.anchors.armed(!!on);
        if (!on) this._canvasHoverOff();
      }
      this._toggleBtn.classList.toggle('active', on);
      this._sh.classList.toggle('arming', on); // mobile: swap the pull-tab for the bottom mode bar
      if (this._lbl) this._lbl.textContent = on ? 'Stop' : 'Comment'; // vertical tab label; icon + badge stay
      if (this._modesBar) this._modesBar.classList.toggle('show', on); // bar shows only while actively commenting
      if (!on) { this._clearMulti(); this._clearArea(); if (this._mcompose) this._mcompose.classList.remove('show'); }
      this._syncFreeze();   // the shield is only active while commenting
      this._setHover(on);
      this._emit('onMode', !!on);
    },
    // Публічна ручка режиму коментування. Потрібна сусіднім оверлеям (інспектор
    // канваса), щоб не тягнутись у приватне й не лишати панель режимів висіти.
    setCommentMode(on) {
      if (this._inited) this._armComment(!!on);
      return this;
    },

    // Toggle comment mode independently of the panel. On desktop, turning it on also
    // opens the side panel for context; on mobile the panel is a full-screen overlay,
    // so we leave it closed (you need to see the page to tap elements — the list
    // button opens the panel to review). Turning it off never touches the panel.
    _toggleComment() {
      if (this.commentMode) { this._armComment(false); }
      else {
        if (!this._isMobile() && !this._panel.classList.contains('show')) this._openPanel();
        this._armComment(true);
      }
    },

    // ---- annotation modes ----
    _toggleMulti(el) {
      const i = this._multiSel.indexOf(el);
      if (i >= 0) { this._multiSel.splice(i, 1); el.classList.remove('cl-msel'); }
      else { this._multiSel.push(el); el.classList.add('cl-msel'); }
      if (this._mccount) this._mccount.textContent = this._multiSel.length;
    },
    _clearMulti() {
      (this._multiSel || []).forEach((el) => el.classList.remove('cl-msel'));
      this._multiSel = [];
      if (this._mccount) this._mccount.textContent = '0';
      if (this._mcta) this._mcta.value = '';
    },
    // Multi: comment from the bottom-right modal on all picked elements.
    _finishMulti() {
      const text = this._mcta ? this._mcta.value.trim() : '';
      if (!this._multiSel.length || !text) { if (this._mcta) this._mcta.focus(); return; }
      const els = this._multiSel.slice();
      const fps = els.map((el) => fingerprint(el, this.target));
      const rect = unionRect(els);   // kept in meta so the selection region is on record
      // Screenshot the closest common ancestor: it shows every picked element in
      // context, and the element render path is the only reliable one.
      let anc = els[0];
      while (anc && anc !== this.target && !els.every((e) => anc.contains(e))) anc = anc.parentElement;
      this._clearMulti();
      this._addComment(els[0], text, '', { mode: 'multi', fps, count: els.length, rect, shotEl: anc || els[0] });
    },
    _clearArea() { if (this._areaBox) { this._areaBox.remove(); this._areaBox = null; } this._area = null; },
    _elementAt(x, y) {
      const el = document.elementFromPoint(x, y);
      return (el && this.target.contains(el) && !this._host.contains(el)) ? el : null;
    },

    _setHover(on) { if (!on && this._hoverEl) { this._hoverEl.classList.remove('cl-hl'); this._hoverEl = null; } },
    _togglePins() {
      this._pinsHidden = !this._pinsHidden;
      this._pins.classList.toggle('hide', this._pinsHidden);
      if (this._eye) {
        this._eye.innerHTML = this._pinsHidden ? icon('eye') : icon('eyeOff');
        const t = this._pinsHidden ? 'Show pins' : 'Hide pins';
        this._eye.setAttribute('data-tip', t); this._eye.setAttribute('aria-label', t);
      }
    },

    /* ---- полотно (етап 2 T-45): ціль — із геометрії кадру, не з DOM ---- */
    _canvasHoverOff() { if (this._hovBox) this._hovBox.style.display = 'none'; this._hovTarget = null; },
    _canvasHover(e) {
      if (this._host.contains(e.target) || this._sh.querySelector('.compose')) { this._canvasHoverOff(); return; }
      const t = typeof this.anchors.hit === 'function' ? this.anchors.hit(e.clientX, e.clientY) : null;
      this._lastPt = { x: e.clientX, y: e.clientY };
      if (!t) { this._canvasHoverOff(); return; }
      if (!this._hovBox) { this._hovBox = document.createElement('div'); this._hovBox.className = 'clhov'; this._sh.appendChild(this._hovBox); }
      const r = t.rect, b = this._hovBox;
      b.style.display = 'block';
      b.style.transform = `translate(${r.left}px,${r.top}px)`;
      b.style.width = r.width + 'px'; b.style.height = r.height + 'px';
      this._hovTarget = t;
    },
    _canvasClick(e) {
      const d = this._downAt;
      if (d && Math.abs(e.clientX - d.x) + Math.abs(e.clientY - d.y) > 4) return;   // це була панорама
      const t = typeof this.anchors.hit === 'function' ? this.anchors.hit(e.clientX, e.clientY) : null;
      if (!t) return;   // не кадр (голова, зазор, «Відкрити») — клік хоста
      e.preventDefault(); e.stopPropagation();
      this._canvasHoverOff();
      this._openCanvasCompose(t);
    },
    // Верх панелі режимів (Element/Text/…) — нижче нього композер не опускається.
    _composeFloor() {
      const b = this._modesBar;
      if (!b || !b.classList.contains('show')) return Infinity;
      return b.getBoundingClientRect().top - 8;
    },
    _openCanvasCompose(t) {
      const existing = this._sh.querySelector('.compose'); if (existing) existing.remove();
      // Повний відбиток і HTML — у фоні, поки людина друкує (прихована рамка).
      t._enrich = typeof this.anchors.enrich === 'function' ? Promise.resolve(this.anchors.enrich(t)).catch(() => null) : null;
      const r = t.rect;
      const box = document.createElement('div');
      box.className = 'compose';
      const tx = (t.fp && t.fp.text || '').slice(0, 50);
      box.innerHTML = `<div class="csel">on &lt;${esc(t.fp && t.fp.tag || '?')}&gt;${tx ? ' · “' + esc(tx) + '”' : ''}</div><textarea placeholder="Leave a change request…"></textarea>
        <div class="row"><button class="cancel">Cancel</button><button class="primary save">Comment</button></div>`;
      this._sh.appendChild(box);
      /* Права межа — за СПРАВЖНІМИ ширинами композера й панелі. Числа 260/340
         DOM-режиму менші за 290/372, і біля панелі кнопка «Comment» ховалась під
         нею — знайдено живим тестом K (клік по «Comment» не доходив). */
      const pw = this._hostOpts ? this._hostInset() : (this._panel.classList.contains('show') ? this._panel.getBoundingClientRect().width : 0);
      const bw = box.offsetWidth || 290;
      box.style.left = Math.max(8, Math.min(r.left, window.innerWidth - pw - bw - 12)) + 'px';
      const top = composeTop({ top: r.top, bottom: r.top + r.height }, box.offsetHeight || 170,
        window.innerHeight, this._composeFloor());
      box.style.top = top + 'px';
      const ta = box.querySelector('textarea'); ta.focus();
      box.querySelector('.cancel').onclick = () => box.remove();
      box.querySelector('.save').onclick = () => {
        const text = ta.value.trim(); if (!text) return;
        this._addCanvasComment(t, text); box.remove();
      };
    },
    _addCanvasComment(t, text) {
      const user = getUser(this.user, this.opts && this.opts.defaultUser);
      const m = t.meta || {};
      // Та сама форма, що в DOM-режимі (`buildContextBundle`) — щоб `inbox.py` і
      // живий вид не розрізняли, звідки пін. HTML дописує `enrich`.
      const ctx = buildContextBundle({ outerHTML: '', text: t.fp && t.fp.text, url: m.url, route: m.route,
        version: m.version, viewport: m.viewport, ts: nowStamp() });
      Object.assign(ctx.meta, { seq: this._nextSeq(), iteration: iterationOf(m.version), mode: 'element',
        anchor: m.anchor || t.anchor, via: m.via || 'overview' });
      const id = genId();
      this.comments.push({
        id, author: user.name, text, status: 'open', fp: t.fp,
        htmlSnapshot: ctx.htmlSnapshot, meta: ctx.meta,
        bornV: this._version(), ts: nowStamp(), _pending: true,
      });
      this._backupNow(); this._render();
      this._finishCanvasComment(id, t);
    },
    // Як `_finishComment`: збагачення → скриншот → (заливка) → ПЕРШИЙ persist.
    // Fail-soft: не встигло — пін зберігається з тим, що є.
    async _finishCanvasComment(id, t) {
      const c = () => this.comments.find((x) => x.id === id);
      try {
        const en = await this._withTimeout(t._enrich, 8000);
        if (c() && en) { if (en.fp) c().fp = en.fp; if (en.htmlSnapshot) c().htmlSnapshot = en.htmlSnapshot; }
      } catch (e) { /* fail-soft */ }
      try {
        const shot = typeof this.anchors.shot === 'function' ? await this._withTimeout(this.anchors.shot(t), 8000) : null;
        if (c() && shot) {
          c().meta.shot = shot;
          if (this.store && typeof this.store.uploadShot === 'function') {
            const url = await this._withTimeout(this.store.uploadShot(id, shot), 8000);
            if (url) c().meta.shotUrl = url;
          }
        }
      } catch (e) { /* fail-soft */ }
      this._persist(); this._render(); this._placePins();
    },

    _openCompose(el, sel, extra) {
      const existing = this._sh.querySelector('.compose'); if (existing) existing.remove();
      const r = el.getBoundingClientRect();
      const box = document.createElement('div');
      box.className = 'compose';
      const rightBound = window.innerWidth - 260 - (this._hostOpts ? this._hostInset() : (this._panel.classList.contains('show') ? 340 : 0));
      box.style.left = Math.max(8, Math.min(r.left, rightBound)) + 'px';
      const m = extra && extra.mode;
      // What is being commented on — shown in every mode (like the text quote), so the target is always clear.
      const desc = (e) => { const t = e.tagName.toLowerCase(); const tx = (e.textContent || '').replace(/\s+/g, ' ').trim(); return '&lt;' + t + '&gt;' + (tx ? ' · “' + esc(tx.slice(0, 50)) + '”' : ''); };
      const note = m === 'multi' ? `${icon('multi', 13)} ${extra.count} elements`
        : m === 'area' ? `${icon('area', 13)} area · ${desc(el)}`
        : sel ? `on: “${esc(sel.slice(0, 120))}”`
        : `on ${desc(el)}`;
      box.innerHTML = `<div class="csel">${note}</div><textarea placeholder="Leave a change request…"></textarea>
        <div class="row"><button class="cancel">Cancel</button><button class="primary save">Comment</button></div>`;
      this._sh.appendChild(box);
      /* Хост: праву межу рахуємо за СПРАВЖНЬОЮ шириною композера (260 — менше за неї) і за місцем, яке тримає хост. */
      if (this._hostOpts) box.style.left = Math.max(8, Math.min(r.left, window.innerWidth - this._hostInset() - (box.offsetWidth || 290) - 12)) + 'px';
      // Vertical placement: below the element, but flip above / clamp so it never runs off-screen.
      const top = composeTop(r, box.offsetHeight || 170, window.innerHeight, this._composeFloor());
      box.style.top = top + 'px';
      const ta = box.querySelector('textarea'); ta.focus();
      box.querySelector('.cancel').onclick = () => box.remove();
      box.querySelector('.save').onclick = () => {
        const text = ta.value.trim(); if (!text) return;
        this._addComment(el, text, sel, extra); box.remove();
      };
    },

    _addComment(el, text, sel, extra) {
      const user = getUser(this.user, this.opts && this.opts.defaultUser);
      const ctx = buildContextBundle({
        outerHTML: el.outerHTML,
        text: el.textContent,
        url: location.href,
        route: location.pathname + location.hash,
        version: this.appVersion,
        viewport: { w: window.innerWidth, h: window.innerHeight },
        ts: nowStamp(),
      });
      ctx.meta.seq = this._nextSeq();   // stable display number, assigned once
      ctx.meta.iteration = iterationOf(this.appVersion);  // канонічна ітерація пина (не born_v — той сесійний)
      if (sel) ctx.meta.sel = sel;               // the exact text the reviewer selected
      if (extra && extra.mode) ctx.meta.mode = extra.mode;      // element|text|multi|area
      if (extra && extra.fps) ctx.meta.fps = extra.fps;         // multi: fingerprints of all picked elements
      if (extra && extra.rect) ctx.meta.rect = extra.rect;      // area: drawn region
      if (extra && extra.count) ctx.meta.count = extra.count;
      try { const where = captureContext(el, this.target, { heading: this.appLocal }); if (where) ctx.meta.ctx = where; } catch (e) { /* контекст — підказка, не умова */ }
      this.comments.push({
        id: genId(), author: user.name, text, status: 'open',
        fp: fingerprint(el, this.target),
        htmlSnapshot: ctx.htmlSnapshot, meta: ctx.meta,
        bornV: this._version(), ts: nowStamp(),
        _pending: true,   // unsynced until _persist confirms — protects it from live-merge drop
      });
      // Пин показуємо одразу (оптимістично) + негайний бекап; РЕАЛЬНИЙ persist
      // (=INSERT=тригер Teams) — у _finishComment, ПІСЛЯ захвату+заливки скриншота,
      // щоб картка несла meta.shotUrl. Панель не форсуємо (можна коментувати закрито).
      this._backupNow(); this._relocate(); this._render();
      const newId = this.comments[this.comments.length - 1].id;
      // Захват — завжди ELEMENT-render (faithful across pages): для element/text це
      // елемент, для area — якір під областю, для multi — спільний предок (extra.shotEl).
      const shotTarget = (extra && extra.shotEl && extra.shotEl.nodeType === 1) ? extra.shotEl : el;
      this._finishComment(newId, shotTarget);
    },

    // Захват скриншота → (за наявності) заливка в Storage → перший persist. Fail-soft:
    // таймаут/помилка захвату або заливки → зберігаємо коментар без скриншота.
    async _finishComment(id, shotTarget) {
      try {
        const shot = await this._withTimeout(this._captureShot(shotTarget), 8000);
        const c = this.comments.find((x) => x.id === id);
        if (c && shot) {
          c.meta = c.meta || {}; c.meta.shot = shot;
          if (this.store && typeof this.store.uploadShot === 'function') {
            const url = await this._withTimeout(this.store.uploadShot(id, shot), 8000);
            if (url) c.meta.shotUrl = url;
          }
        }
      } catch (e) { /* fail-soft */ }
      this._persist(); this._render(); this._placePins();
    },

    // target = an element. Element renders are the only html2canvas path that
    // stays faithful across pages; coordinate-cropped document renders drift.
    async _captureShot(target) {
      try {
        const h2c = await loadShotLib();
        const base = { backgroundColor: '#ffffff', scale: 1, useCORS: true, logging: false };
        let canvas;
        if (target && target.nodeType === 1) {
          target.classList.remove('cl-hl');            // don't bake the hover outline into the shot
          canvas = await h2c(target, base);
        } else { return null; }
        const maxW = 360, k = Math.min(1, maxW / (canvas.width || maxW)) || 1;
        const out = document.createElement('canvas');
        out.width = Math.max(1, Math.round(canvas.width * k));
        out.height = Math.max(1, Math.round(canvas.height * k));
        out.getContext('2d').drawImage(canvas, 0, 0, out.width, out.height);
        return out.toDataURL('image/jpeg', 0.6);      // small; stored inline in the comment meta
      } catch (e) { return null; }
    },

    // The core loop: call after the UI is regenerated.
    regenerated() {
      this._bumpVersion();                       // the new version is now current
      let resolved = 0, carried = 0;
      for (const c of this.comments) {
        if (c.status !== 'open') continue;
        const res = classify(c.fp, this.target);
        if (res.decision === 'RESOLVE') {
          c.status = 'resolved'; c.resolveReason = res.reason; c.resolvedV = this._version(); c.meta = c.meta || {}; c.meta.resolvedAt = Date.now(); resolved++;
        } else {
          c._el = res.el; c.fp = fingerprint(res.el, this.target); carried++; // re-baseline to displayed version
        }
      }
      this._persist(); this._render(); this._placePins();
      return { resolved, carried };
    },

    _watch() {
      let t; const obs = new MutationObserver(() => { clearTimeout(t); t = setTimeout(() => this.regenerated(), 400); });
      obs.observe(this.target, { childList: true, subtree: true, characterData: true });
      this._obs = obs;
    },

    /** Пін без видимого елемента в цьому документі (не знайдено або схований). */
    _offscreen(c) {
      return !c._el || !c._el.isConnected || c._el.getClientRects().length === 0;
    },

    _relocate() { // find each open comment's current element in the live DOM
      // Полотно: елемента в цьому документі немає — точку дає постачальник.
      if (this.anchors) { for (const c of this.comments) c._el = null; return; }
      for (const c of this.comments) {
        // Поза-скоупний пін (чужа ітерація) не якоримо → _placePins його не ставить.
        if (c.status !== 'open' || !this._inScope(c)) { c._el = null; continue; }
        try { const m = findMatch(c.fp, this.target); c._el = (m.el && m.score >= MATCH_THRESHOLD) ? m.el : null; }
        catch (e) { c._el = null; } // one malformed comment must never break the panel
      }
    },

    _placePins() {
      if (this.anchors) return this._placeCanvasPins();
      this._pins.innerHTML = '';
      this._hidePinPop();
      for (const c of this.comments) {
        if (c.status !== 'open' || !c._el) continue;
        const r = c._el.getBoundingClientRect();
        if (r.width === 0 && r.height === 0) continue;
        const p = document.createElement('div');
        p.className = 'pin'; p.textContent = this.appLocal ? '' : this._seqOf(c);
        p.style.left = (r.left + 10) + 'px'; p.style.top = (r.top + 10) + 'px';
        p.onclick = () => this._focusCard(c.id);
        p.onmouseenter = () => this._showPinPop(p, c);   // hover → preview the comment beside the pin
        p.onmouseleave = () => this._hidePinPop();
        this._pins.appendChild(p);
      }
    },

    /* Піни полотна ключовані: на кожен кадр камери міняється лише transform, DOM
       не перебудовується (DOM-режим робить innerHTML='' — на скролі це дешево,
       на 60 кадрах панорами ні). Позаекранні — за край трансформом, а не
       display:none: перемикання display — це layout. Позицію несе обгортка
       `.cp`, ховер — сам `.pin`: `transition` на трансформі-позиції змусив би
       піни відставати від полотна на кожному кадрі. */
    _placeCanvasPins() {
      this._hidePinPop();
      /* Панель прибита до верху ВІКНА (`top:0`). У сторінці це верх рамки, а в
         оболонці — верх її смуги: шапка панелі (вкладки «Клод/Команда», ✕)
         ховалась під смугою — знайдено живим оглядом. Верх полотна дає
         постачальник; пишемо змінну лише на зміні. */
      const top = this.anchors.top ? Math.max(0, Math.round(this.anchors.top() || 0)) : 0;
      if (top !== this._clTop) { this._clTop = top; this._sh.style.setProperty('--cl-top', top + 'px'); }
      const pins = this._pinsHidden ? []
        : this.comments.filter((c) => c.status === 'open' && this._inScope(c));
      const want = pins.length ? (this.anchors.place(pins) || []) : [];
      const byId = new Map(pins.map((c) => [c.id, c]));
      const els = this._pinEls || (this._pinEls = new Map());
      const seen = new Set();
      for (const it of want) {
        seen.add(it.key);
        let w = els.get(it.key);
        if (!w) {
          w = document.createElement('div'); w.className = 'cp';
          const p = document.createElement('div'); p.className = 'pin'; w.appendChild(p);
          p.onclick = () => {
            const x = w._item;
            if (x.off) this._focusCards(x.ids);
            else if (x.cluster) this.anchors.revealKey(x.key);
            else this._focusCard(x.ids[0]);
          };
          p.onmouseenter = () => {
            const x = w._item; if (x.cluster || x.off) return;
            const c = this.comments.find((y) => y.id === x.ids[0]); if (c) this._showPinPop(p, c);
          };
          p.onmouseleave = () => this._hidePinPop();
          els.set(it.key, w); this._pins.appendChild(w);
        }
        w._item = it;
        const c = it.cluster || it.off ? null : byId.get(it.ids[0]);
        // Підпис лічильника «поза кадром» — від хоста (мова його інтерфейсу).
        const label = it.off ? String(it.label || it.ids.length)
          : it.cluster ? String(it.ids.length) : (this.appLocal || !c ? '' : String(this._seqOf(c)));
        if (w.firstChild.textContent !== label) w.firstChild.textContent = label;
        w.firstChild.classList.toggle('cluster', !!it.cluster);
        w.firstChild.classList.toggle('off', !!it.off);
        w.style.transform = it.vis ? `translate3d(${it.x}px,${it.y}px,0)` : 'translate3d(-9999px,-9999px,0)';
      }
      for (const [k, w] of els) if (!seen.has(k)) { w.remove(); els.delete(k); }
      // Колесо рухає камеру без руху миші — рамка наведення мусить їхати разом.
      if (this.commentMode && this._lastPt) this._canvasHover({ clientX: this._lastPt.x, clientY: this._lastPt.y, target: null });
    },

    // Hover preview: a small card with the comment shown next to its pin.
    _showPinPop(pin, c) {
      const pop = this._pinpop; if (!pop) return;
      const badge = c.status === 'open'
        ? '<span class="badge open"><span class="d"></span>open</span>'
        : '<span class="badge resolved"><span class="d"></span>resolved</span>';
      pop.innerHTML = `<div class="pptop"><span class="seq">${this._seqOf(c)}</span><span class="who">${esc(c.author)}</span>${badge}</div><div class="ppbody">${esc(c.text)}</div>`;
      pop.classList.add('show');
      const r = pin.getBoundingClientRect(), gap = 10, pad = 10;
      const pw = pop.offsetWidth, ph = pop.offsetHeight;
      let left = r.right + gap;
      if (left + pw > window.innerWidth - this._hostInset() - pad) left = r.left - pw - gap;   // flip to the left near the edge
      left = Math.max(pad, left);
      let top = r.top + r.height / 2 - ph / 2;
      top = Math.max(pad, Math.min(top, window.innerHeight - ph - pad));
      pop.style.left = left + 'px'; pop.style.top = top + 'px';
    },
    _hidePinPop() { if (this._pinpop) this._pinpop.classList.remove('show'); },

    // Кілька карток разом (лічильник «поза кадром» на полотні): до першої, блимають усі.
    _focusCards(ids) {
      if (this._hostOpts) { if (ids && ids.length) this._emit('onSelect', ids[0]); return; }
      if (!ids || !ids.length) return;
      this._focusCard(ids[0]);
      for (const id of ids.slice(1)) {
        const el = this._sh.querySelector('#c' + id);
        if (!el) continue;
        el.classList.remove('flash'); void el.offsetWidth; el.classList.add('flash');
        setTimeout(() => el.classList.remove('flash'), 1400);
      }
    },

    // Clicking a pin opens the panel, scrolls to its card and flashes it.
    _focusCard(id) {
      if (this._hostOpts) { this._emit('onSelect', id); return; }
      this._openPanel();
      const el = this._sh.querySelector('#c' + id);
      if (!el) return;
      el.scrollIntoView({ block: 'center', behavior: 'smooth' });
      el.classList.remove('flash'); void el.offsetWidth; el.classList.add('flash'); // restart anim
      setTimeout(() => el.classList.remove('flash'), 1400);
    },

    // Reverse of _focusCard: clicking a card scrolls the page to its element and
    // flashes that element (host DOM). Only works for a comment matched to a live element.
    _focusElement(id) {
      if (this.anchors) {   // полотно: не скрол до елемента, а переліт камери до піна
        const c = this.comments.find((x) => x.id === id);
        if (c) this.anchors.reveal(c);
        return;
      }
      const c = this.comments.find((x) => x.id === id); if (!c) return;
      // Comment made on another page → navigate there (multi-page apps). The widget
      // re-inits on that page and its pin/element will be present.
      const route = location.pathname + location.hash;
      if (c.meta && c.meta.route && c.meta.route !== route && c.meta.url) { location.href = c.meta.url; return; }
      let el = c._el;
      if (!el) { const m = findMatch(c.fp, this.target); el = (m.el && m.score >= MATCH_THRESHOLD) ? m.el : null; c._el = el; }
      /* Елемента немає або він схований (інший крок `@switch`, закритий оверлей):
         раніше тут був мовчазний `return` — дизайнер клікав і не розумів, що
         сталось (fb-06102026-c38f46). Тепер — знімок елемента, якщо є. */
      if (!el || el.getClientRects().length === 0) {
        const src = c.meta && (c.meta.shot || c.meta.shotUrl);
        if (src) this._openLightbox(src);
        return;
      }
      el.scrollIntoView({ block: 'center', behavior: 'smooth' });
      el.classList.remove('cl-el-flash'); void el.offsetWidth; el.classList.add('cl-el-flash');
      setTimeout(() => el.classList.remove('cl-el-flash'), 1500);
    },

    // Full-screen preview of a comment's screenshot; click anywhere (or Esc) to close.
    _openLightbox(src) {
      if (!src) return;
      const lb = document.createElement('div'); lb.className = 'cllb';
      const img = document.createElement('img'); img.src = src; img.alt = 'comment snapshot';
      lb.appendChild(img); lb.onclick = () => lb.remove();
      this._sh.appendChild(lb);
    },

    _render() {
      // Sort: creation order (new/old), or by close-recency (closed = most recently resolved first).
      // Close time lives in meta.resolvedAt (jsonb → persists through Supabase); tolerate the
      // old top-level field and comments with no recorded close time (fall back to newest-created).
      const closedAt = (c) => (c.meta && c.meta.resolvedAt) || c.resolvedAt || 0;
      const bySort = this._sort === 'closed'
        ? (a, b) => (closedAt(b) - closedAt(a)) || (this._seqOf(b) - this._seqOf(a))
        : (a, b) => (this._seqOf(a) - this._seqOf(b)) * (this._sort === 'old' ? 1 : -1);
      const open = this.comments.filter((c) => c.status === 'open' && this._inScope(c)).sort(bySort);
      const hist = this.comments.filter((c) => c.status === 'resolved' && this._inScope(c)).sort(bySort);
      // Відкриті пини ВІДОМИХ інших ітерацій (не поточна, не legacy) — не на макеті,
      // а окремою секцією з ручним переносом. Legacy сюди не потрапляє (воно в scope).
      const prevIter = this.comments
        .filter((c) => c.status === 'open' && !this._inScope(c) && this._pinIter(c) != null)
        .sort(bySort);
      // Badge on the FAB: open comments on THIS page (by route; legacy w/o route count as here).
      // Полотно: «ця сторінка» — усе полотно, тобто всі сторінки ітерації на екрані.
      const route = location.pathname + location.hash;
      const hereOpen = this.anchors ? open.length
        : open.filter((c) => !c.meta || !c.meta.route || c.meta.route === route).length;
      if (this._cbadge) { this._cbadge.textContent = hereOpen; this._cbadge.hidden = hereOpen === 0; }
      if (this._speektxt) this._speektxt.textContent = hereOpen ? `Show comments · ${hereOpen}` : 'Show comments';
      if (this._total) this._total.textContent = this.comments.length;
      // Tabs: show only the active set (Open | Closed), not both stacked. Counts are totals.
      const tab = this._tab || 'open';
      if (this._tabOpen) { this._tabOpen.textContent = `Open (${open.length})`; this._tabOpen.classList.toggle('active', tab === 'open'); }
      if (this._tabClosed) { this._tabClosed.textContent = `Closed (${hist.length})`; this._tabClosed.classList.toggle('active', tab === 'resolved'); }
      let list = tab === 'resolved' ? hist : open;
      // Search filter (text / author / #number / date / selected phrase), within
      // the active tab. "#12" is an exact comment-number lookup; anything else is
      // a substring match over everything shown on the card.
      const q = this._query;
      if (q) {
        const mNum = q.match(/^#(\d+)$/);
        list = mNum
          ? list.filter((c) => this._seqOf(c) === +mNum[1])
          : list.filter((c) => (`#${this._seqOf(c)} ${c.text} ${c.author} ${c.ts || ''} ${(c.meta && c.meta.sel) || ''}`).toLowerCase().includes(q));
      }
      const empty = q ? 'No comments match your search.'
        : (tab === 'resolved' ? 'No closed comments yet.'
          : 'No open comments yet. Pull the “Comment” tab, then click any element on the page.');
      const mainHtml = list.length ? list.map((c) => this._card(c, tab === 'resolved')).join('') : `<div class="empty">${empty}</div>`;
      // Пини інших ітерацій — окремою згортаною секцією (тільки на вкладці Open),
      // не на макеті. Кожен можна свідомо перенести копією на поточну ітерацію.
      const prevSection = (tab === 'open' && prevIter.length)
        ? `<details class="cl-prev"><summary>${icon('sort', 13)} З попередніх ітерацій (${prevIter.length})</summary>`
          + prevIter.map((c) => `<div class="cl-prev-item"><div class="cl-prev-meta">Іт.${this._pinIter(c)} · ${esc(c.author)}</div><div class="cl-prev-text">${esc(c.text)}</div><button class="ghost cl-carry" data-cl-act="carry" data-cl-id="${c.id}">${icon('arrow', 13)} Перенести сюди</button></div>`).join('')
          + `</details>`
        : '';
      this._list.innerHTML = mainHtml + prevSection;
      this._placePins();
      this._emitChange();
    },
    _card(c, isHist) {
      // Inline edit mode for this card.
      if (c.id === this._editingId) {
        return `<div class="c editing" id="c${c.id}">
          <div class="top"><span class="seq">${this._seqOf(c)}</span><span class="who">${esc(c.author)}</span></div>
          <div class="editform">
            <textarea class="editta">${esc(c.text)}</textarea>
            <div class="acts"><button class="primary" data-cl-act="edit-save" data-cl-id="${c.id}" data-tip="Save" aria-label="Save">${icon('check')}</button><button class="ghost" data-cl-act="edit-cancel" data-cl-id="${c.id}" data-tip="Cancel" aria-label="Cancel">${icon('x')}</button></div>
          </div></div>`;
      }
      const badge = c.status === 'open'
        ? '<span class="badge open"><span class="d"></span>open</span>'
        : '<span class="badge resolved"><span class="d"></span>resolved</span>';
      const mm = c.meta && c.meta.mode;
      const mtag = mm && mm !== 'element'
        ? `<span class="mtag">${mm === 'multi' ? icon('multi', 12) + (c.meta.count || '') : mm === 'area' ? icon('area', 12) + 'area' : icon('text', 12) + 'text'}</span>` : '';
      // Technical anchor info (pinned tag / version / fp / html snapshot) stays in the stored
      // comment for AI export & debugging, but is intentionally NOT shown to the reviewer.
      const when = `<div class="when">${icon('clock', 12)}${c.ts ? markMatch(c.ts, this._query) : 'time unknown'}</div>`;
      /* Ширина — поруч із часом, не в технічному блоці: вона міняє СМИСЛ
         коментаря, а не пояснює його походження. */
      const vp = (c.meta && c.meta.viewport) || null;
      const vptag = vp && vp.w
        ? `<span class="vptag">${vpBand(vp.w)} · ${vp.w}×${vp.h || '?'}</span>` : '';
      const acts = c.status === 'open'
        ? `<button class="ghost" data-cl-act="resolve" data-cl-id="${c.id}" data-tip="Resolve" aria-label="Resolve comment">${icon('check')}</button>`
        : `<button class="ghost" data-cl-act="reopen" data-cl-id="${c.id}" data-tip="Reopen" aria-label="Reopen comment">${icon('reopen')}</button>`;
      const route = location.pathname + location.hash;
      // Полотно: «на іншій сторінці» не буває — клік по картці летить до піна камерою.
      const elsewhere = !this.anchors && !!(c.meta && c.meta.route && c.meta.route !== route);
      const sel = c.meta && c.meta.sel ? `<div class="csel">on: “${markMatch(String(c.meta.sel).slice(0, 120), this._query)}”</div>` : '';
      const shot = c.meta && c.meta.shot ? `<img class="shot" src="${c.meta.shot}" alt="snapshot at comment time">` : '';
      const other = elsewhere ? `<div class="otherpage">${icon('arrow', 13)}on another page — open</div>` : '';
      /* Пін є, а його елемента зараз немає на екрані (інший крок/стан SPA) —
         кажемо це вголос, а не мовчимо на кліку (fb-06102026-c38f46). */
      const offscreen = !this.anchors && !elsewhere && c.status === 'open' && this._offscreen(c);
      const where = offscreen ? ctxLine(c.meta && c.meta.ctx) : '';
      const off = offscreen ? `<div class="offscreen">${icon('area', 13)}<span>Елемента зараз немає на екрані — інший крок чи стан сторінки${where ? `. Був: ${esc(where)}` : ''}</span></div>` : '';
      // Jump-to-element affordance, moved into the card header as an icon-only arrow.
      const jumpTip = elsewhere ? 'Open page' : offscreen ? 'Show snapshot' : 'Go to element';
      const jump = c.status === 'open' ? `<span class="jump" data-tip="${jumpTip}" aria-label="${jumpTip}">${icon('arrow', 15)}</span>` : '';
      return `<div class="c ${isHist ? 'hist' : ''}" id="c${c.id}">
        <div class="top"><span class="seq">${this._seqOf(c)}</span><span class="who">${markMatch(c.author, this._query)}</span>${mtag}${badge}${jump}</div>
        <div class="body">${markMatch(c.text, this._query)}</div>${sel}${when}${vptag ? `<div class="when">${icon('area', 12)}${vptag}</div>` : ''}${other}${off}${shot}
        <div class="acts"><button data-cl-act="edit" data-cl-id="${c.id}" data-tip="Edit" aria-label="Edit">${icon('edit')}</button>${acts}<button class="danger" data-cl-act="delete" data-cl-id="${c.id}" data-tip="Delete" aria-label="Delete">${icon('trash')}</button></div></div>`;
    },

    // Durability: nothing a reviewer typed should ever be lost. We mirror to
    // localStorage synchronously (survives a crash or a failed network write),
    // then write the primary store; only after the primary confirms do we clear
    // the "pending" marks. _recoverBackup() re-pushes anything still pending.
    // Синхронний бекап у localStorage (переживає крах чи невдалу мережу). Кличемо
    // і з _persist, і одразу на створення пина — бо реальний persist тепер чекає
    // на захват+заливку скриншота, і без цього було б вікно втрати.
    //
    // ⛔ У бекап ідуть ЛИШЕ неконфірмовані піни (`_pending`) — відновлення й так
    // бере тільки їх. Раніше тут лежав увесь список зі знімком HTML і скріном у
    // base64, ключі не витіснялись, і за кілька задач localStorage (~5 млн
    // символів на origin) забивався: будь-який наступний запис падав мовчки
    // в `catch {}`, і пін жив лише в памʼяті вікна (fb 05.11.2026).
    _backupNow() {
      const pending = this.comments.filter((c) => c._pending)
        .map(stripRuntime).map((c) => ({ ...c, _pending: true }));
      let store = null;
      try { store = localStorage; } catch (e) {}
      this._backupOk = writeBackup(store, this._backupKey, pending);
      if (!this._backupOk) console.warn('[comment-layer] local backup failed (storage full?) — unsynced comments live only in this window');
    },
    _withTimeout(p, ms) {
      return Promise.race([Promise.resolve(p),
        new Promise((res) => setTimeout(() => res(null), ms))]);
    },
    async _persist() {
      const plain = this.comments.map(stripRuntime);
      this._backupNow();
      try {
        const res = this.store.save(plain);
        if (res && typeof res.then === 'function') await res;   // Supabase adapter throws on failure
        this.comments.forEach((c) => { c._pending = false; });  // confirmed synced
        this._backupNow();                                      // нічого не висить → ключ прибрано
      } catch (e) {
        console.warn('[comment-layer] primary store save failed; comments kept in local backup for retry', e && e.message);
      }
    },
    _recoverBackup() {
      let backup = [];
      try { backup = JSON.parse(localStorage.getItem(this._backupKey) || '[]'); } catch (e) { return; }
      if (!Array.isArray(backup)) return;
      const have = new Set(this.comments.map((c) => c.id));
      // Only truly-unsynced comments (still _pending) that the primary store is
      // missing — a comment that synced then got deleted by someone else is NOT
      // pending, so it is correctly left deleted rather than resurrected.
      const missing = backup.filter((c) => c && c.id && c._pending && !have.has(c.id))
        .map(({ _pending, ...c }) => ({ ...c, _pending: true })); // stay pending until re-sync confirms
      if (!missing.length && !backup.some((c) => c && c._pending)) {
        // Старий формат: синхронізований список цілком. Відновлювати нічого — звільняємо місце.
        try { localStorage.removeItem(this._backupKey); } catch (e) {}
      }
      if (missing.length) {
        this.comments = this.comments.concat(missing);
        this._persist();
        console.warn('[comment-layer] recovered ' + missing.length + ' unsynced comment(s) from local backup');
      }
    },
    _version() { return this._ver || (this._ver = 1); },

    // --- Скоуп пінів за ітерацією. Пін живе на СВОЇЙ ітерації; legacy (нечитана
    // ітерація) видно скрізь; якщо поточна ітерація не визначена — скоуп вимкнено.
    _pinIter(c) { const m = c && c.meta; return iterationOf(m && (m.iteration != null ? m.iteration : m.version)); },
    _curIter() { return iterationOf(this.appVersion); },
    _inScope(c) {
      const cur = this._curIter();
      if (cur == null) return true;               // немає поточної → показуємо все (безпечно)
      const pi = this._pinIter(c);
      return pi == null || pi === cur;            // legacy → скрізь; інакше — тільки своя
    },
    // Ручний перенос-КОПІЯ пина з іншої ітерації на поточну. Новий id + новий seq,
    // той самий fp (спробує заякоритись на поточному DOM; не вийде — лишиться в
    // списку без крапки). Оригінал не чіпаємо — історія на своїй ітерації.
    _carryToCurrent(id) {
      const src = this.comments.find((x) => x.id === id);
      if (!src) return;
      const copy = {
        id: genId(), author: getUser(this.user, this.opts && this.opts.defaultUser).name, text: src.text, status: 'open',
        fp: src.fp, htmlSnapshot: src.htmlSnapshot,
        meta: Object.assign({}, src.meta, {
          iteration: this._curIter(), version: this.appVersion,
          route: location.pathname + location.hash, seq: this._nextSeq(),
          carriedFrom: { id: src.id, iteration: this._pinIter(src) },
        }, this.anchors ? carryCanvasMeta(src.meta, this._curIter()) : null),
        bornV: this._version(), ts: nowStamp(), _pending: true,
      };
      this.comments.push(copy);
      this._persist(); this._relocate(); this._render(); this._placePins();
    },
    // Stable display number, assigned once at creation and persisted in meta.seq
    // so deleting one comment never renumbers the others. Legacy comments without
    // a stored seq fall back to their position.
    _seqOf(c) { return (c.meta && c.meta.seq) || (this.comments.indexOf(c) + 1); },
    _nextSeq() {
      const maxExisting = this.comments.reduce((m, c) => Math.max(m, (c.meta && c.meta.seq) || 0), 0);
      const next = Math.max(this._seqHigh || 0, maxExisting) + 1;   // never reuse a deleted number
      this._seqHigh = next;
      try { localStorage.setItem(this._seqHighKey, String(next)); } catch (e) {}
      return next;
    },
    // Assign a stable number to any comment that predates meta.seq, so numbers
    // are unique and never shift. Persisted once, then a no-op on later loads.
    _backfillSeq() {
      let max = this.comments.reduce((m, c) => Math.max(m, (c.meta && c.meta.seq) || 0), 0);
      let changed = false;
      for (const c of this.comments) {
        if (!(c.meta && c.meta.seq)) { c.meta = c.meta || {}; c.meta.seq = ++max; changed = true; }
      }
      if (changed) this._persist();
    },
    _bumpVersion() { this._ver = this._version() + 1; },

    // Manual status controls (complement the automatic version-aware resolve).
    resolveComment(id) {
      const c = this.comments.find((x) => x.id === id); if (!c || c.status === 'resolved') return;
      c.status = 'resolved'; c.resolvedV = this._version(); c.resolveReason = 'resolved manually'; c.meta = c.meta || {}; c.meta.resolvedAt = Date.now(); c._el = null;
      this._persist(); this._render(); this._placePins();
    },
    reopenComment(id) {
      const c = this.comments.find((x) => x.id === id); if (!c || c.status === 'open') return;
      c.status = 'open'; c.resolvedV = null; c.resolveReason = null;
      if (c.meta) delete c.meta.resolvedAt;   // close-time no longer applies (it drives the "recently closed" sort)
      delete c.resolvedAt;                    // legacy top-level field, same reason
      const m = findMatch(c.fp, this.target);
      c._el = (m.el && m.score >= MATCH_THRESHOLD) ? m.el : null;
      this._persist(); this._render(); this._placePins();
    },
    removeComment(id) {
      const c = this.comments.find((x) => x.id === id); if (!c) return;
      if (typeof confirm === 'function' && !confirm('Delete this comment permanently?')) return;
      if (this.store.remove) this.store.remove([id]);          // hard-delete in backing store
      this.comments = this.comments.filter((x) => x.id !== id);
      this._persist(); this._render(); this._placePins();
    },

    // public helpers
    open() { this._openPanel(); },
    toggle() { this._panel.classList.contains('show') ? this._closePanel() : this._openPanel(); },
    getComments() { return this.comments.map(stripRuntime); },

    /* ---- API хоста (Deai 0.26.0) ---- */
    /** Скільки px справа у вікні коментатора займає ХОСТ (його панель): композер і підказки не лягають під неї. Без хоста,
     *  без колбека, нечисло чи виняток — 0. */
    _hostInset() {
      const h = this._hostOpts;
      if (!h || typeof h.rightInset !== 'function') return 0;
      try { const n = +h.rightInset(); return Number.isFinite(n) && n > 0 ? n : 0; } catch (e) { return 0; }
    },
    _emit(name, arg) {
      const h = this._hostOpts;
      if (!h || typeof h[name] !== 'function') return;
      try { h[name](arg); } catch (e) { /* хост не сміє зламати коментатор */ }
    },
    /** `onChange` зі знімком — лише з хостом і після `init`; збій знімка не ламає ні `init`, ні `_render`. */
    _emitChange() {
      if (!this._hostOpts || !this._inited) return;
      let s;
      try { s = this.snapshot(); } catch (e) { return; }
      this._emit('onChange', s);
    },
    /** Знімок для панелі хоста: копії без `_el`/`_pending`/`fp`/`htmlSnapshot` + `n` (номер піна), `scope`
     *  (`current` — ця ітерація чи legacy, `earlier` — інша відома ітерація, `other` — решта), `where` (`here` /
     *  `elsewhere` — інша сторінка / `offscreen` — елемента нема на екрані), `iter` (ітерація піна), `pending`. */
    snapshot() {
      const route = location.pathname + location.hash;
      const where = (c) => {
        if (!this._inScope(c)) return 'here';   // не якоримо поза скоупом (_relocate) — «поза кадром» тут не про них
        if (!this.anchors && c.meta && c.meta.route && c.meta.route !== route) return 'elsewhere';
        if (!this.anchors && c.status === 'open' && this._offscreen(c)) return 'offscreen';
        return 'here';
      };
      const scope = (c) => (this._inScope(c) ? 'current' : (this._pinIter(c) != null ? 'earlier' : 'other'));
      return {
        version: this.appVersion, iteration: this._curIter(), pinsHidden: !!this._pinsHidden,
        comments: this.comments.map((c) => {
          const { _el, _pending, fp, htmlSnapshot, ...rest } = c;
          return Object.assign({}, rest, rest.meta && typeof rest.meta === 'object' ? { meta: Object.assign({}, rest.meta) } : {},
            { n: this._seqOf(c), scope: scope(c), where: where(c), iter: this._pinIter(c), pending: !!_pending });
        }),
      };
    },
    /** Те саме, що клік по картці в панелі коментатора: скрол і спалах елемента (полотно — камера до піна). */
    focus(id) {
      const c = this._inited && this.comments.find((x) => x.id === id);
      if (c && this._inScope(c)) this._focusElement(id);   // поза скоупом елемент не якорений: нечіткий збіг блимнув би чужим
    },
    carry(id) { if (this._inited) this._carryToCurrent(id); },
    editComment(id, text) {
      const v = String(text == null ? '' : text).trim();
      const c = this.comments.find((x) => x.id === id);
      if (!c || !v) return false;
      c.text = v; c._pending = true;
      this._persist(); this._render();
      return true;
    },
    openShot(id) {
      const c = this.comments.find((x) => x.id === id);
      const src = c && c.meta && (c.meta.shot || c.meta.shotUrl);
      if (src) this._openLightbox(src);
    },
    togglePins() { if (!this._inited) return false; this._togglePins(); this._render(); return !!this._pinsHidden; },
    reset() { this.comments = []; this._ver = 1; this._persist(); this._render(); this._placePins(); },
  };

  function stripRuntime(c) { const { _el, _pending, ...rest } = c; return rest; }
  // Верх композера: під елементом, інакше над ним, інакше — притиснутий донизу,
  // але НЕ нижче `floor` (верх панелі режимів). Панель лежить вище за z-index, і
  // на великому <section> кнопки форми опинялись під нею: клік по «Comment»
  // вмикав режим Text, коментар не йшов (fb 05.11.2026, рамка 978px).
  function composeTop(r, boxH, viewH, floor) {
    const vpad = 12, limit = Math.min(viewH - vpad, floor);
    let top = r.bottom + 8;
    if (top + boxH > limit) {
      const above = r.top - boxH - 8;
      top = above >= vpad ? above : Math.max(vpad, limit - boxH);
    }
    return top;
  }
  // ── Локальний бекап (fb 05.11.2026). Чисті функції, сховище — параметром:
  // тест годує їх підробленим localStorage з квотою.
  const BACKUP_PREFIX = 'comment-layer:backup:';
  // Пін без важкого: скрін у base64 і повний outerHTML. Текст, якір і решта
  // знімка лишаються — відновлений пін без картинки кращий за втрачений.
  function lightPin(c) {
    const out = { ...c };
    if (out.meta && out.meta.shot) { out.meta = { ...out.meta }; delete out.meta.shot; }
    if (out.htmlSnapshot && out.htmlSnapshot.outerHTML) {
      out.htmlSnapshot = { ...out.htmlSnapshot }; delete out.htmlSnapshot.outerHTML;
    }
    return out;
  }
  // Звільнити місце за рахунок ЧУЖИХ ключів бекапу: без жодного `_pending`
  // ключ відновленню не потрібен (старий формат, синхронізований список) —
  // геть; з `_pending` — лишаємо, але без важкого. Повертає, чи щось звільнилось.
  function evictStaleBackups(store, keepKey) {
    const keys = [];
    for (let i = 0; i < store.length; i++) {
      const k = store.key(i);
      if (k && k.indexOf(BACKUP_PREFIX) === 0 && k !== keepKey) keys.push(k);
    }
    let freed = false;
    for (const k of keys) {
      let list = null;
      try { list = JSON.parse(store.getItem(k) || 'null'); } catch (e) {}
      const pending = Array.isArray(list) ? list.filter((c) => c && c._pending) : [];
      if (!pending.length) { store.removeItem(k); freed = true; continue; }
      const before = store.getItem(k).length;
      const light = JSON.stringify(pending.map(lightPin));
      if (light.length < before) { try { store.setItem(k, light); freed = true; } catch (e) {} }
    }
    return freed;
  }
  // Записати бекап проєкту. Порожній список — прибрати ключ. Далі: повний →
  // (звільнити чужі мертві ключі) → повний → легкий. Скрін втрачаємо лише
  // тоді, коли місця нема й після чистки. `false` — не вдалось нічого: тоді хоч
  // не мовчимо.
  function writeBackup(store, key, list) {
    if (!store) return false;
    if (!list.length) { try { store.removeItem(key); } catch (e) {} return true; }
    const attempt = (l) => { try { store.setItem(key, JSON.stringify(l)); return true; } catch (e) { return false; } };
    if (attempt(list)) return true;
    let freed = false;
    try { freed = evictStaleBackups(store, key); } catch (e) {}
    if (freed && attempt(list)) return true;
    return attempt(list.map(lightPin));
  }
  // Union bounding box (viewport coords) of several elements — used to screenshot a multi-selection.
  function unionRect(els) {
    let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
    for (const el of els) {
      const r = el.getBoundingClientRect();
      x1 = Math.min(x1, r.left); y1 = Math.min(y1, r.top);
      x2 = Math.max(x2, r.right); y2 = Math.max(y2, r.bottom);
    }
    return isFinite(x1) ? { x: x1, y: y1, w: x2 - x1, h: y2 - y1 } : null;
  }
  /* Перенос піна з минулої ітерації, зроблений на ПОЛОТНІ (T-45). У DOM-режимі
     копія бере версію й маршрут сторінки, де стоїть віджет, — там це і є
     сторінка піна. На полотні віджет стоїть в оболонці: `appVersion` — лише
     ітерація, маршрут — `/app/`, тож копія загубила б сторінку й поїхала б на
     неявну `main`. Тут сторінку беремо з самого піна: суфікс версії, маршрут і
     адреса живого виду — з новою ітерацією. */
  function carryCanvasMeta(m, iter) {
    m = m || {};
    const v = String(m.version == null ? '' : m.version).split('/');
    const out = { route: m.route || null, version: v.length > 1 ? [iter].concat(v.slice(1)).join('/') : String(iter) };
    if (m.url) {
      try { const u = new URL(m.url); if (u.searchParams.has('it')) u.searchParams.set('it', 'it' + iter); out.url = u.href; }
      catch (e) { /* битий url лишаємо як був */ }
    }
    return out;
  }
  // DOM-режим: чи прихована рамка, у якій живе віджет (оболонка показує
  // «Огляд» замість сторінки). Крос-origin батько — не знаємо, вважаємо видимою.
  function hiddenFrame() {
    try { const f = window.frameElement; return !!f && f.getClientRects().length === 0; } catch (e) { return false; }
  }
  function esc(s) { return String(s).replace(/[&<>"]/g, (m) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[m])); }
  // Escape for HTML, then wrap case-insensitive matches of the search query in <mark> (amber highlighter).
  function markMatch(text, q) {
    const s = esc(text == null ? '' : text);
    if (!q) return s;
    const eq = esc(q).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    try { return s.replace(new RegExp('(' + eq + ')', 'ig'), '<mark class="clmark">$1</mark>'); } catch (e) { return s; }
  }
  // Local time in the reviewer's own timezone. Format: DD.MM.YYYY HH:MM.
  function nowStamp() {
    try {
      const parts = new Intl.DateTimeFormat('en-GB', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit', hour12: false,
      }).formatToParts(new Date());
      const g = (t) => (parts.find((x) => x.type === t) || {}).value || '';
      return `${g('day')}.${g('month')}.${g('year')} ${g('hour')}:${g('minute')}`;
    } catch { return ''; }
  }
  // Globally-unique comment id. Client-assigned sequential ids collide across
  // reviewers (two clients both start at 1) → upsert(onConflict:id) overwrites.
  // A UUID is unique without server coordination, so multi-reviewer save is safe.
  // Lazy-load html2canvas from CDN only when a screenshot is first captured, so the
  // core bundle stays dependency-free. Fails soft: no lib → no screenshot, comment still works.
  let _shotLibPromise = null;
  function loadShotLib() {
    if (typeof window !== 'undefined' && window.html2canvas) return Promise.resolve(window.html2canvas);
    if (_shotLibPromise) return _shotLibPromise;
    _shotLibPromise = new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = 'https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js';
      s.onload = () => resolve(window.html2canvas);
      s.onerror = () => reject(new Error('html2canvas load failed'));
      document.head.appendChild(s);
    });
    return _shotLibPromise;
  }
  function genId() {
    try { if (globalThis.crypto && globalThis.crypto.randomUUID) return globalThis.crypto.randomUUID(); } catch (e) {}
    return 'c-' + nowStamp().replace(/\D/g, '') + '-' + Math.random().toString(36).slice(2, 10);
  }

  /* Окремий інстанс (T-45). Потрібен оболонці канваса: канал «Клод/Команда»
     там перемикається без перезавантаження документа, а `init` — одноразовий
     (`_inited`). Глобальний `CommentLayer` лишається інстансом за замовчуванням,
     і чужі хости (INTEGRATION.md) цього не помічають. */
  CommentLayer.create = function () { const o = Object.create(CommentLayer); o._inited = false; o._dead = false; return o; };
  CommentLayer.destroy = function () {
    if (!this._inited) return;
    /* Режим коментування — ПЕРШИМ: `_armComment(false)` каже хосту `armed(false)`.
       Без цього прапорець оболонки лишався піднятим, і клік по кадру після
       перемикання каналу вже не відкривав кадр (ревʼю T-45, D3). */
    /* Хост сам почав знищення (зміна каналу, вихід з «Огляду») і про нього знає: колбеків із destroy нема — інакше
       `onMode(false)` закривав би панель оболонки при кожному перемиканні каналу. */
    this._hostOpts = null;
    if (this.commentMode) this._armComment(false);
    this._dead = true;   // підписки сховища без відписки гасить _onExternalChange
    if (this.store && typeof this.store.close === 'function') { try { this.store.close(); } catch (e) {} }
    if (this._hlStyle) this._hlStyle.remove();
    (this._keyTargets || []).forEach((w) => { try { w.removeEventListener('keydown', this._keyHandler, true); } catch (e) {} });
    document.removeEventListener('click', this._clickHandler, true);
    document.removeEventListener('mouseup', this._upHandler, true);
    document.removeEventListener('mousedown', this._areaDown, true);
    document.removeEventListener('mousemove', this._areaMove, true);
    document.removeEventListener('mouseup', this._areaUp, true);
    document.removeEventListener('mousemove', this._moveHandler, true);
    document.removeEventListener('selectionchange', this._selHandler);
    document.removeEventListener('pointerdown', this._downHandler, true);
    if (this._host) this._host.remove();
    this._pinEls = null;
    this._inited = false;
  };

  // expose the algorithm too, for adapters / tests
  CommentLayer._algo = { fingerprint, classify, findMatch, captureContext, ctxLine };
  global.CommentLayer = CommentLayer;
})(window);
