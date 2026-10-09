/**
 * Правила дерева сторінок — клієнтський близнюк `app/pages_model.py`.
 *
 * Авторитет — сервер (він пише файл і перевіряє те саме); цей модуль потрібен,
 * щоб ДО запиту сказати дизайнеру «сюди не можна й чому» і показати, куди
 * саме ляже сторінка. Обидва рушії ганяють `tests/fixtures/tree-rules.json`:
 * розійдуться — впадуть обидва тести.
 *
 * Чистий модуль: ні DOM, ні fetch, ні `t()` — лише коди помилок; переклад
 * робить викликач (`ERR_KEY`).
 */

export const KINDS = ["folder", "page", "state"];
export const MAX_DEPTH = 32;

/** Код відмови → ключ словника (`app/i18n.js`). */
export const ERR_KEY = {
  "state-outside-page": "treeErrStateOutsidePage",
  "state-has-children": "treeErrStateHasChildren",
  cycle: "treeErrCycle",
  self: "treeErrSelf",
  "not-siblings": "treeErrNotSiblings",
  "too-deep": "treeErrTooDeep",
  "bad-kind": "treeErrBadKind",
  "not-found": "treeErrNotFound",
  stale: "treeStale",
  busy: "treeBusy",
  "bad-id": "treeErrBadId",
  "bad-index": "treeErrBadIndex",
  "dup-id": "treeErrDupId",
  "empty-name": "treeErrEmptyName",
  "bad-where": "treeErrBadWhere",
  "bad-ids": "treeErrBadIds",
  corrupt: "treeErrCorrupt",
};

/** Ключ словника для коду або null (невідомий код — викликач бере загальний текст).
    hasOwn, а не `ERR_KEY[code]`: «toString» не повинен виявитись «ключем». */
export function errKey(code) {
  return typeof code === "string" && Object.hasOwn(ERR_KEY, code) ? ERR_KEY[code] : null;
}

/* `\w` у Python 3 — юнікодний (кирилиця проходить), у JS — лише ASCII.
   `\p{L}\p{N}` з прапорцем `u` — найближче дзеркало; розходження на рідкісних
   знаках (комбіновані діакритики) — не наш випадок: id робить `_slug`.
   Прив'язка ^…$ без `m` у JS не збігається перед завершальним `\n` — так само
   суворо, як `fullmatch` у Python. */
const ID_RE = /^[\p{L}\p{N}_-]+$/u;

const isIdString = (id) => typeof id === "string" && ID_RE.test(id);

export function kindOf(node, parentKind = null) {
  if (KINDS.includes(node?.kind)) return node.kind;
  if (node?.isGroup) return "folder";
  return parentKind === "page" ? "state" : "page";
}

/** [{page, parent, depth, kind}] — усі рівні, порядок дерева (форма `pm.flatten`).
    Чекає структурно валідного дерева (вузли-обʼєкти): охоронці — у `precheck` applyMove. */
export function flatten(pages, depth = 0, parent = null, parentKind = null, out = []) {
  for (const pg of pages ?? []) {
    const kind = kindOf(pg, parentKind);
    out.push({ page: pg, parent, depth, kind });
    flatten(pg.children, depth + 1, pg.id, kind, out);
  }
  return out;
}

/**
 * Id усіх вузлів, видимих у превʼю (теки теж у наборі) — близнюк
 * `pages_model._visible`. Правило одне на весь інструмент (рішення власника
 * 30.09.2026): вузол видимий, коли ні він, ні жоден предок не має буквального
 * `published: false`; явне `true` на нащадку схованого предка нічого не скасовує.
 */
export function visibleIds(pages, out = new Set()) {
  for (const pg of pages ?? []) {
    if (pg.published === false) continue;
    out.add(pg.id);
    visibleIds(pg.children, out);
  }
  return out;
}

/** {node, list, index, parent} або null; `list` — сам масив у дереві. Дерево — структурно валідне. */
export function findNode(pages, id, parent = null) {
  const list = pages ?? [];
  for (let i = 0; i < list.length; i += 1) {
    if (list[i].id === id) return { node: list[i], list, index: i, parent };
    const sub = findNode(list[i].children, id, list[i]);
    if (sub) return sub;
  }
  return null;
}

/** [корінь, …, вузол] або []. Дерево — структурно валідне. */
export function pathOf(pages, id) {
  for (const pg of pages ?? []) {
    if (pg.id === id) return [pg];
    const sub = pathOf(pg.children, id);
    if (sub.length) return [pg, ...sub];
  }
  return [];
}

/** null або {code} — ті самі коди й ТОЙ САМИЙ порядок перевірок, що `_validate_node`. */
export function validate(pages) {
  const seen = new Set();
  const walk = (list, depth, parentKind, inPage) => {
    for (const pg of list ?? []) {
      if (depth > MAX_DEPTH) return { code: "too-deep" };
      // typeof першим: id-число чи відсутній id не повинні дійти до RegExp
      if (!isIdString(pg?.id)) return { code: "bad-id" };
      if (seen.has(pg.id)) return { code: "dup-id" };
      seen.add(pg.id);
      if (typeof pg.name !== "string" || !pg.name.trim()) return { code: "empty-name" };
      if ("kind" in pg && !KINDS.includes(pg.kind)) return { code: "bad-kind" };
      const kind = kindOf(pg, parentKind);
      // довжина, а не істинність масиву: порожній `children: []` — валідний.
      // Не-список (обʼєкт/рядок/число — файл правили руками) — corrupt, як у Python.
      const kids = pg.children || [];
      if (!Array.isArray(kids)) return { code: "corrupt" };
      if (kind === "state") {
        if (!inPage) return { code: "state-outside-page" };
        if (kids.length) return { code: "state-has-children" };
      }
      const e = walk(kids, depth + 1, kind, inPage || kind === "page");
      if (e) return e;
    }
    return null;
  };
  return walk(pages, 1, null, false);
}

/** Лише «верхні» з вибраних, у порядку дерева. Дерево — структурно валідне, `ids` — масив. */
export function topIds(pages, ids) {
  const want = new Set(ids);
  return flatten(pages)
    .filter((f) => want.has(f.page.id)
      && !pathOf(pages, f.page.id).slice(0, -1).some((a) => want.has(a.id)))
    .map((f) => f.page.id);
}

const clone = (v) => JSON.parse(JSON.stringify(v));

/**
 * Дзеркало `_precheck`: у кожного вузла id-рядок за правилом id, явний `kind`
 * ∈ KINDS. Повний `validate` на вході не годиться (відхилив би легасі-дерево),
 * а без цього вузол без id ламав би обхід, а невалідний kind закріплення
 * перетворило б на виведений.
 */
function precheck(pages) {
  for (const pg of pages ?? []) {
    if (pg === null || typeof pg !== "object" || Array.isArray(pg) || !isIdString(pg.id)) {
      return { err: "bad-id" };
    }
    if ("kind" in pg && !KINDS.includes(pg.kind)) return { err: "bad-kind" };
    // як `_children_list`: не-список — corrupt, а не обхід символів рядка
    if (pg.children && !Array.isArray(pg.children)) return { err: "corrupt" };
    const e = precheck(pg.children);
    if (e) return e;
  }
  return null;
}

/**
 * Дзеркало `pm.op_move`: перенести `ids` під `parent` на `index` серед дітей
 * ПІСЛЯ виймання (обрізається до меж). {tree} | {err} | {noop:true, tree}.
 * Вхід не мутується.
 */
export function applyMove(pages, ids, parent, index) {
  if (!Number.isInteger(index)) return { err: "bad-index" };
  if (!Array.isArray(ids)) return { err: "bad-ids" };
  const bad = precheck(pages);
  if (bad) return bad;
  const t = clone(pages);
  if (ids.some((id) => !findNode(t, id))) return { err: "not-found" };
  const top = topIds(t, ids);
  // тип і батько кожного кореня — з ЦІЛОГО дерева ДО виймання (для закріплення)
  const was = new Map(flatten(t).map((f) => [f.page.id, { parent: f.parent, kind: f.kind }]));
  if (parent !== null) {
    if (top.includes(parent) || pathOf(t, parent).some((a) => top.includes(a.id))) return { err: "cycle" };
    const p = findNode(t, parent);
    if (!p) return { err: "not-found" };
    if (flatten(t).find((f) => f.page === p.node).kind === "state") return { err: "state-has-children" };
  }
  const moved = [];
  const touched = new Set();
  for (const id of top) {
    const r = findNode(t, id);
    touched.add(was.get(id).parent);
    // Тип без `kind` виводиться з БАТЬКА, тож зміна батька тихо перетворила б
    // легасі-стан на сторінку: закріплюємо явно, але лише коли батько справді
    // міняється (перестановка лишається no-op) і лише без явного `kind`
    // (невалідний явний не мусить «відмитись» у виведений).
    if (!("kind" in r.node) && was.get(id).parent !== parent) r.node.kind = was.get(id).kind;
    r.list.splice(r.index, 1);
    moved.push(r.node);
  }
  let dest = t;
  if (parent !== null) {
    const p = findNode(t, parent).node;
    if (!p.children) p.children = [];
    dest = p.children;
  }
  const at = Math.max(0, Math.min(index, dest.length));
  dest.splice(at, 0, ...moved);
  // Порожній `children: []` прибираємо ЛИШЕ на вузлах, яких торкнулась дія
  // (старі батьки й місце призначення): сторонній порожній `children` не наша
  // справа, інакше «нічого не змінилось» перестало б бути no-op.
  touched.add(parent);
  for (const pid of touched) {
    if (pid === null) continue;
    const n = findNode(t, pid)?.node;
    if (n && Array.isArray(n.children) && !n.children.length) delete n.children;
  }
  const e = validate(t);
  if (e) return { err: e.code };
  if (JSON.stringify(t) === JSON.stringify(pages)) return { noop: true, tree: t };
  return { tree: t };
}

/**
 * Чи можна прибрати вузол, піднявши його дітей на його місце — дзеркало
 * `pm.op_unwrap` (закріплення типів дітей ДО підняття + повний `validate`).
 * Потрібне діалогу видалення: пропонувати дію, яку сервер однаково відхилить
 * (`state-outside-page` для кореневої сторінки зі станами), — це кнопка-пастка.
 * Вхід не мутується.
 */
export function canUnwrap(pages, id) {
  if (precheck(pages)) return false;
  const t = clone(pages);
  const r = findNode(t, id);
  if (!r) return false;
  const was = new Map(flatten(t).map((f) => [f.page.id, f.kind]));
  const kids = r.node.children ?? [];
  for (const ch of kids) if (!("kind" in ch)) ch.kind = was.get(ch.id);
  r.list.splice(r.index, 1, ...kids);
  return validate(t) === null;
}

/**
 * Зона перетягування → (parent, index) → applyMove.
 * where: 'before' | 'after' | 'inside' (у кінець) | 'first' (першою дитиною) | 'end' (кінець кореня);
 * інше — `bad-where` (мовчки в корінь не кладемо).
 * Результат ЗАВЖДИ {err?, noop?, tree?, parent, index, ids} — рівно те, що йде в
 * `POST /api/page-move`; на відмові parent/index = null, ids = «верхні» вибрані.
 * `index` — позиція серед дітей батька ПІСЛЯ виймання, а НЕ індекс видимого рядка.
 * Дерево — структурно валідне (перевірка вхідних даних — у precheck applyMove).
 */
export function planMove(pages, ids, targetId, where) {
  const top = Array.isArray(ids) ? topIds(pages, ids) : [];
  const fail = (err) => ({ err, parent: null, index: null, ids: top });
  if (!Array.isArray(ids)) return fail("bad-ids");
  if (!["before", "after", "inside", "first", "end"].includes(where)) return fail("bad-where");
  // topIds мовчки губить невідомі id — а сервер відмовив би not-found
  if (ids.some((id) => !findNode(pages, id))) return fail("not-found");
  if (targetId !== null && top.includes(targetId)) return fail("self");
  if (targetId !== null && pathOf(pages, targetId).slice(0, -1).some((a) => top.includes(a.id))) return fail("cycle");
  let parent = null;
  let index = Number.MAX_SAFE_INTEGER;
  if (where === "end") {
    // явна гілка: корінь, у кінець (MAX_SAFE_INTEGER обріжеться в applyMove)
    parent = null;
  } else if (where === "inside" || where === "first") {
    parent = targetId;
    if (where === "first") index = 0;
  } else {
    const r = findNode(pages, targetId);
    if (!r) return fail("not-found");
    parent = r.parent ? r.parent.id : null;
    // індекс рахуємо ПІСЛЯ виймання тих, кого тягнуть: інакше сторінка, яку
    // тягнуть униз, ставала б на одну нижче (пастка зсуву, `page-order.js`)
    const rest = r.list.filter((x) => !top.includes(x.id)).map((x) => x.id);
    index = rest.indexOf(targetId) + (where === "after" ? 1 : 0);
  }
  const res = applyMove(pages, top, parent, index);
  if (res.err) return { ...res, parent: null, index: null, ids: top };
  // у запит на сервер — фактична позиція, а не гігантське «в кінець»
  if (top.length) {
    const dest = parent === null ? res.tree : findNode(res.tree, parent)?.node.children;
    const at = (dest ?? []).findIndex((x) => x.id === top[0]);
    if (at >= 0) index = at;
  }
  return { ...res, parent, index, ids: top };
}

/** Лічильник для згорнутого вузла: усі нащадки (на будь-якій глибині), сам вузол не рахується. */
export function statsOf(node, parentKind = null) {
  const s = { pages: 0, states: 0, folders: 0 };
  const own = kindOf(node, parentKind);
  for (const f of flatten(node.children, 0, node.id, own)) {
    if (f.kind === "page") s.pages += 1;
    else if (f.kind === "state") s.states += 1;
    else s.folders += 1;
  }
  return s;
}

/**
 * Видимі рядки панелі: [{page, parent, depth, kind}] з глибиною ВІДНОСНО кореня
 * показу. Рядок видно, коли розгорнуті ВСІ предки (не лише прямий) — інакше
 * онук при згорнутому дідові лишався б у списку без батька.
 * `focus` — id вузла, чиї діти стають коренем показу (предки самого фокуса не
 * враховуються: вони поза показом); невідомий id = без фокуса, а не порожня
 * панель. `filter` — підрядок назви без регістру: видно збіги та їхніх предків,
 * гілки до збігів розкриті незалежно від `expanded`. Вхід не мутується.
 */
export function visibleRows(pages, { expanded, focus = null, filter = "" }) {
  const whole = flatten(pages);
  const anchor = focus ? whole.find((f) => f.page.id === focus) : null;
  const offset = anchor ? anchor.depth + 1 : 0;
  const all = anchor ? flatten(anchor.page.children, offset, anchor.page.id, anchor.kind) : whole;
  const shift = (f) => ({ ...f, depth: f.depth - offset });
  const q = filter.trim().toLowerCase();
  if (q) {
    const keep = new Set();
    for (const f of all) {
      if (!String(f.page.name ?? "").toLowerCase().includes(q)) continue;
      for (const a of pathOf(pages, f.page.id)) keep.add(a.id);
    }
    return all.filter((f) => keep.has(f.page.id)).map(shift);
  }
  const byId = new Map(all.map((f) => [f.page.id, f]));
  // батько поза показом (корінь фокуса) в `byId` не знайдеться — ланцюг там і обривається
  const open = (f) => {
    for (let p = f.parent; p && byId.has(p); p = byId.get(p).parent) if (!expanded.has(p)) return false;
    return true;
  };
  return all.filter(open).map(shift);
}

/**
 * Сусід видимого рядка за напрямком (+1 вниз, -1 вгору) — id або null на краю.
 * Невідомий поточний (рядок зник під час перемальовки) дає перший/останній, а
 * не мовчання: клавіша не має «губитись». Чиста, бо клавіатурі панелі треба
 * рахувати наступний рядок від ЗБЕРЕЖЕНОГО фокуса, а не від застарілого DOM.
 */
export function stepRow(rows, id, dir) {
  if (!rows.length) return null;
  const i = rows.findIndex((r) => r.page.id === id);
  if (i < 0) return rows[dir > 0 ? 0 : rows.length - 1].page.id;
  return rows[i + dir]?.page.id ?? null;
}

/** Перша дитина вузла, коли вона одразу ВИДИМА (розгорнуто); інакше null. */
export function firstChildRow(rows, id) {
  const i = rows.findIndex((r) => r.page.id === id);
  return i >= 0 && rows[i + 1]?.parent === id ? rows[i + 1].page.id : null;
}

/** Id від `from` до `to` включно у видимому порядку (в обидва боки); null, коли котрогось нема. */
export function rowRange(rows, from, to) {
  const a = rows.findIndex((r) => r.page.id === from);
  const b = rows.findIndex((r) => r.page.id === to);
  if (a < 0 || b < 0) return null;
  return rows.slice(Math.min(a, b), Math.max(a, b) + 1).map((r) => r.page.id);
}
