/**
 * Піни коментарів на «Огляді» (T-45) — ЧИСТА модель: ні DOM, ні fetch. Склейка
 * з comment-layer і мережею — у `overview-comments.js`.
 *
 * Екран рахується рівно тією формулою, що трансформ світу в `applyT`:
 * `translate(cvx,cvy) scale(cvscale)` від лівого верхнього кута полотна, тобто
 * екран = кут полотна + cam + світ·масштаб. Друга формула розійшлась би з першою
 * на першому ж зумі — і піни поїхали б від кадрів.
 */
import { RESERVED_Q, stateQuery } from "./flow-model.js";

/** Кадр на екрані вужчий за це — його піни злипаються в один лічильник: на
 *  bird-view 30 окремих кружків на 128-піксельному кадрі — це шум, а не зміст. */
export const CLUSTER_W = 240;
/** Той самий зсув +10/+10 від кута елемента, що `_placePins` живого виду:
 *  інакше пін на «Огляді» й у сторінці стояв би в різних місцях того самого елемента. */
export const PIN_OFFSET = 10;
/** Переліт до піна не лишає його дрібним — як у Claude Design (≥0.5). */
export const REVEAL_MIN_SCALE = 0.5;
/** Неявна сторінка ітерації — `pm.IMPLICIT_ID` у `pages_model.py`. Тег версії
 *  такої сторінки — чисте число (`"3"`), без суфікса. */
export const IMPLICIT_PAGE = "main";

/**
 * Куди належить пін: сторінка й стан. Сторінка — з тегу версії
 * (`page_version_tag`: `"3/stattia"` або `"3"` для неявної), бо його пише той
 * самий сервер, що й кадри; url — лише запасний шлях для legacy-тегів (`it1`),
 * які ітерації й сторінки не несуть. Стан — хвіст url без наших параметрів,
 * нормалізований ТІЄЮ САМОЮ `stateQuery`, якою рахується ключ кадру стану.
 */
export function pinTarget(c) {
  const m = (c && c.meta) || {};
  const v = m.version == null ? "" : String(m.version);
  let url = null;
  try { url = m.url ? new URL(m.url) : null; } catch { url = null; }
  const state = {};
  if (url) for (const [k, val] of url.searchParams) if (!RESERVED_Q.has(k)) state[k] = val;
  const stateQ = stateQuery(state);
  const [head, ...rest] = v.split("/");
  if (/^\d+$/.test(head)) return { page: rest.length ? rest.join("/") : IMPLICIT_PAGE, stateQ };
  const p = url && url.searchParams.get("page");
  return p ? { page: p, stateQ } : null;
}

export const cardMatches = (card, t) => Boolean(t) && card.page === t.page
  && stateQuery(card.state) === t.stateQ;

/* Кеш цілі — по ОБʼЄКТУ піна (і ключа кадру — по обʼєкту кадру). Розбір url на
   кожному кадрі камери коштував ~8мс на кадр при 264 пінах (замір T-45, етап 3).
   WeakMap, а не id: сховище на кожну зовнішню зміну дає НОВІ обʼєкти, тож
   змінена адреса чи версія підхоплюється сама, без інвалідації. */
const targetOf = new WeakMap();
const cachedTarget = (c) => {
  if (!c || typeof c !== "object") return pinTarget(c);
  if (!targetOf.has(c)) targetOf.set(c, pinTarget(c));
  return targetOf.get(c);
};
const cardKeyOf = new WeakMap();
const keyOf = (page, stateQ) => `${page}\u0000${stateQ}`;
const cardKey = (card) => {
  if (!cardKeyOf.has(card)) cardKeyOf.set(card, keyOf(card.page, stateQuery(card.state)));
  return cardKeyOf.get(card);
};

/** Кадри, на яких цей пін має стояти. У флоу сторінка буває на кількох — пін
 *  на кожному (спека §3.4). */
export const cardsOfPin = (c, cards) => {
  const t = pinTarget(c);
  return t ? cards.filter((k) => cardMatches(k, t)) : [];
};

/**
 * Світова точка піна на кадрі. `e` — запис геометрії (координати документа
 * сторінки, 1:1 з пікселями знімка), `card.h` — висота ЗНІМКА (голова кадру
 * `head` окремо, її додає розкладка).
 * null: елемента немає, він 0×0 (живий вид такий пін теж не ставить), або
 * точка нижче обрізу кадру (>8000px — пін не на картинці).
 */
export function pinWorld(card, e, anchor, head) {
  if (!e || (e.w <= 0 && e.h <= 0)) return null;
  const fx = anchor && Number.isFinite(anchor.fx) ? anchor.fx : null;
  const fy = anchor && Number.isFinite(anchor.fy) ? anchor.fy : null;
  const lx = fx === null ? e.x + PIN_OFFSET : e.x + fx * e.w;
  const ly = fy === null ? e.y + PIN_OFFSET : e.y + fy * e.h;
  if (ly < 0 || ly > card.h) return null;
  return { x: card.x + lx, y: card.y + head + ly };
}

const inView = (x, y, v) => x >= v.left && x <= v.left + v.w && y >= v.top && y <= v.top + v.h;

/**
 * Що малювати: `[{key, x, y, ids, cluster, off, vis}]` в екранних координатах.
 * `worldOf(pin, card)` дає склейка (з кешованої геометрії): `{x,y}` — точка;
 * `null` — ВІДОМО, що місця на кадрі нема (елемент зник, нижче обрізу, кадр без
 * геометрії); `undefined` — ще не знаємо (геометрія їде).
 *
 * Рішення власника 29.09.2026: лічильник на дрібному зумі — лише піни, що
 * мають місце на кадрі (інакше «3» на відстані ставало двома пінами зблизька);
 * решта — окремим лічильником «поза кадром» над кадром (`off`, підпис дає хост).
 * Позаекранні не викидаються, а йдуть з `vis:false`: comment-layer тримає їхні
 * вузли й лише відсуває за край — інакше панорама щокадру створювала б і
 * видаляла DOM.
 */
export function layoutPins({ pins, cards, cam, cardW, view, worldOf }) {
  const out = [];
  const clustered = cardW * cam.scale < CLUSTER_W;
  const sx = (wx) => view.left + cam.x + wx * cam.scale;
  const sy = (wy) => view.top + cam.y + wy * cam.scale;
  // Індекс «сторінка+стан → піни» — один прохід по пінах на кадр, а не по
  // пінах на КОЖЕН кадр полотна (було O(кадри × піни) розборів url).
  const byKey = new Map();
  for (const p of pins) {
    const t = cachedTarget(p);
    if (!t) continue;
    const k = keyOf(t.page, t.stateQ);
    const list = byKey.get(k);
    if (list) list.push(p); else byKey.set(k, [p]);
  }
  for (const card of cards) {
    const mine = byKey.get(cardKey(card));
    if (!mine) continue;
    const placed = [], off = [];
    for (const p of mine) {
      const w = worldOf(p, card);
      if (w) placed.push([p, w]);
      else if (w === null) off.push(p.id);
      // undefined — геометрія ще їде: ні на кадрі, ні «поза» — чекаємо
    }
    if (clustered) {
      if (placed.length) {
        // правий верхній кут кадру: там лічильник не накриває зміст
        const x = sx(card.x + cardW), y = sy(card.y);
        out.push({ key: `k:${card.id}`, x, y, ids: placed.map(([p]) => p.id), cluster: true, off: false, vis: inView(x, y, view) });
      }
    } else {
      for (const [p, w] of placed) {
        const x = sx(w.x), y = sy(w.y);
        out.push({ key: `p:${p.id}@${card.id}`, x, y, ids: [p.id], cluster: false, off: false, vis: inView(x, y, view) });
      }
    }
    if (off.length) {
      // над лівим верхнім кутом кадру — над головою, під підписом ряду
      const x = sx(card.x), y = sy(card.y);
      out.push({ key: `o:${card.id}`, x, y, ids: off, cluster: false, off: true, vis: inView(x, y, view) });
    }
  }
  return out;
}

/** Камера перельоту: точка — у центр полотна, масштаб не дрібніший за
 *  `minScale` і не більший за 1 (кадр знято 1:1, роздувати нема чого). */
export function revealCam(pt, cam, view, minScale = REVEAL_MIN_SCALE) {
  const scale = Math.min(1, Math.max(cam.scale, minScale));
  return { x: view.w / 2 - pt.x * scale, y: view.h / 2 - pt.y * scale, scale };
}

/* ── Етап 2 T-45: створення коментаря на «Огляді» ───────────────────────────
   Наведення й клік — чиста арифметика по геометрії кадру: жодного DOM
   сторінки під рукою, тому підсвітка миттєва на будь-якому зумі. */

/**
 * Кадр під світовою точкою і локальна точка в координатах ЗНІМКА. Голова кадру
 * (підпис, «Відкрити ↗») не ціль: коментар на ній не мав би елемента.
 */
export function cardAt(cards, wx, wy, cardW, head) {
  for (const card of cards) {
    const lx = wx - card.x, ly = wy - card.y - head;
    if (lx >= 0 && lx <= cardW && ly >= 0 && ly <= card.h) return { card, lx, ly };
  }
  return null;
}

/**
 * Елемент під точкою: найГЛИБШИЙ, що її містить (далі менша площа, далі
 * пізніший у документі). Порядку малювання геометрія не знає, тож «найглибший»
 * — найближче до того, що дав би `elementFromPoint` у живому виді; і дизайнер
 * бачить ціль підсвіткою ДО кліку. Невидимі (`hid`), прозорі для миші (`pe:0`)
 * і 0×0 не беруться — браузер у живому виді їх теж не дав би.
 */
export function hitElement(els, lx, ly) {
  let best = -1, bd = -1, ba = Infinity;
  for (let i = 0; i < els.length; i++) {
    const e = els[i];
    if (!(e.w > 0 && e.h > 0) || e.hid || e.pe === 0) continue;
    if (lx < e.x || lx > e.x + e.w || ly < e.y || ly > e.y + e.h) continue;
    const d = (e.path || []).length, a = e.w * e.h;
    if (d > bd || (d === bd && a <= ba)) { best = i; bd = d; ba = a; }
  }
  return best;
}

/**
 * Ціль нового коментаря: відбиток — із запису геометрії (той самий
 * `fingerprint`, знятий затвором), точка — частка кліку всередині елемента
 * (`meta.anchor`, як у Claude), `meta` — рівно те, що пише живий вид: адреса
 * `/commented` цієї сторінки й стану, тег версії `page_version_tag`, ширина
 * полотна як вьюпорт.
 */
export function targetFor({ card, e, lx, ly, cam, view, head, it, iterNum, channel, canvasW, origin }) {
  const s = cam.scale;
  const anchor = { fx: e.w ? (lx - e.x) / e.w : 0, fy: e.h ? (ly - e.y) / e.h : 0 };
  return {
    key: `${card.id}#${(e.path || []).join(">")}`,
    card,
    fp: { tag: e.tag, stableId: e.stableId ?? null, text: e.text, textHash: e.textHash,
          structHash: e.structHash, styleHash: e.styleHash, path: e.path },
    anchor,
    rect: { left: view.left + cam.x + (card.x + e.x) * s, top: view.top + cam.y + (card.y + head + e.y) * s,
            width: e.w * s, height: e.h * s },
    geo: e,
    meta: {
      url: `${origin}/commented?it=${encodeURIComponent(it)}&page=${encodeURIComponent(card.page)}`
        + `&ch=${encodeURIComponent(channel)}${stateQuery(card.state)}`,
      route: "/commented",
      version: card.page === IMPLICIT_PAGE ? String(iterNum) : `${iterNum}/${card.page}`,
      viewport: { w: canvasW, h: 900 },
      anchor,
      via: "overview",
    },
  };
}
