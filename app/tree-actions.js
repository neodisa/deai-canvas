/**
 * Чисті рішення дій над деревом шарів (B4): що показати в меню, що написати в
 * діалозі видалення, як пройти масову дію й як не пустити два запити разом.
 * Жодного DOM і fetch — усе, що в `app.js` ламалось би тихо, тут перевіряється
 * юніт-тестами (`tests/tree-actions.test.mjs`).
 */
import { canUnwrap, flatten, planMove, topIds } from "./tree-model.js";

/** Скільки назв показує діалог видалення; решта — рядком «…і ще N». */
export const DELETE_LIST_CAP = 30;

/**
 * Пункти контекстного меню в порядку показу. Тип вузла вирішує набір: стан не
 * вміщає тек, тека не перемикається в стан, «розгрупувати» має сенс лише для
 * теки з вмістом; множинний вибір — лише групувати й видаляти.
 */
export function pageMenuItems({ kind = "page", hasChildren = false, hasParent = false,
  multi = false, canUp = false, canDown = false } = {}) {
  if (multi) return ["group", "delete"];
  const out = [];
  if (kind !== "state") out.push("folder");
  out.push("rename", "group");
  if (kind === "folder" && hasChildren) out.push("ungroup");
  if (canUp) out.push("up");
  if (canDown) out.push("down");
  if (hasParent) out.push("out");
  if (hasChildren && kind !== "state") out.push("focus");
  if (kind !== "folder") out.push("kind");
  out.push("pub", "delete");
  return out;
}

/** Єдиний вибраний вузол, інакше відкрита сторінка (на ньому діє меню/палітра). */
export function treeTarget(panelSel, pickedPage) {
  return panelSel.size === 1 ? [...panelSel][0] : (pickedPage || null);
}

/** Що загортати в теку: увесь вибір, інакше відкрита сторінка, інакше нічого. */
export function groupTargetIds(panelSel, pickedPage) {
  if (panelSel.size) return [...panelSel];
  return pickedPage ? [pickedPage] : [];
}

/**
 * Модель діалогу видалення для ОДНОГО й для БАГАТЬОХ вузлів однаково: список
 * того, що зникне (вибрані корені разом із нащадками — вкладені вибрані не
 * дублюються), обрізаний до 30 назв.
 *   kind 'yesno' — нічого вкладеного й один вузол: просте питання;
 *   kind 'choice' — є що перелічити; `unwrap` лише коли ціль ОДНА, має дітей
 *   (прибрати теку, вміст підняти) і підняття валідне за правилами дерева
 *   (кореневу сторінку зі станами так не прибрати) — для вибору з багатьох така
 *   дія неоднозначна.
 * Порожній результат (`ids` нема в дереві) — `null`.
 */
export function deleteDialogModel(pages, ids) {
  const top = topIds(pages, ids);
  if (!top.length) return null;
  const flat = flatten(pages);
  const byId = new Map(flat.map((f) => [f.page.id, f]));
  if (top.length === 1) {
    const node = byId.get(top[0]).page;
    const inside = flatten(node.children ?? []).map((f) => f.page.name);
    if (!inside.length) return { kind: "yesno", ids: top, names: [], more: 0, unwrap: false };
    // unwrap — лише коли сервер це прийме (`canUnwrap` ганяє ті самі правила)
    return { kind: "choice", ids: top, unwrap: canUnwrap(pages, top[0]), titleKey: "delTreeTitle",
      titleArgs: [node.name, inside.length], ...cap(inside) };
  }
  const all = [];
  for (const id of top) {
    all.push(byId.get(id).page.name,
      ...flatten(byId.get(id).page.children ?? []).map((f) => f.page.name));
  }
  return { kind: "choice", ids: top, unwrap: false, titleKey: "delManyTitle",
    titleArgs: [top.length, all.length], ...cap(all) };
}
function cap(list) {
  return { names: list.slice(0, DELETE_LIST_CAP), more: Math.max(0, list.length - DELETE_LIST_CAP) };
}

/**
 * Виконати `step(id)` по черзі. Перед КОЖНИМ кроком питаємо `stillValid()`:
 * якщо дизайнер перемкнув ітерацію, решта id належить іншому дереву, і
 * виконати їх означало б видалити чуже. Крок, що повернув хибне, зупиняє цикл
 * (ревізія вже не та). → {done, failed, stopped}: `failed` — id кроку, що не
 * вдався (або порожньо), `stopped` — зупинено через `stillValid`.
 */
export async function runSequential(ids, step, { stillValid = () => true } = {}) {
  const done = [];
  const failed = [];
  let stopped = false;
  for (const id of ids) {
    if (!stillValid()) { stopped = true; break; }
    if (await step(id)) done.push(id);
    else { failed.push(id); break; }
  }
  return { done, failed, stopped };
}

/**
 * Замок «запит дерева в дорозі». `run(fn)` повертає `null` без виклику, якщо
 * вже зайнято; інакше виконує `fn` і ЗНІМАЄ замок навіть на винятку — інакше
 * один збій назавжди глушив би панель. `onChange(busy)` — для класу в DOM.
 */
export function treeBusyGate(onChange = () => {}) {
  let busy = false;
  return {
    get busy() { return busy; },
    async run(fn) {
      if (busy) return null;
      busy = true; onChange(true);
      try { return await fn(); }
      finally { busy = false; onChange(false); }
    },
  };
}

/**
 * Єдине повідомлення після масової дії. Причина відмови кроку мусить дожити до
 * людини: окремий `tell` кроку й окремий підсумок скасовували б один одного
 * (оверлей один), тож крок мовчить, а причину несе ось ця фраза.
 *   зупинено через зміну ітерації → `null` (людина вже в іншому дереві);
 *   усе вдалось → `null`;
 *   один вузол → сама причина;
 *   кілька, з причиною → `delPartialWhy`, без причини → `delPartial`.
 */
export function composeDeleteNote(t, { done, total, why = "", stopped = false }) {
  if (stopped || done >= total) return null;
  if (total === 1) return why || null;
  return why ? t("delPartialWhy", done, total, why) : t("delPartial", done, total);
}

/**
 * Зона кидка на рядок за позицією курсора → `where` для `planMove`.
 * Контейнер (не стан) ділиться 25/50/25: верх — перед, середина — ВСЕРЕДИНУ,
 * низ — після; стан нічого не вміщає, тож навпіл. Нижня зона розгорнутого
 * контейнера з дітьми — «першою дитиною»: лінія «після» під відкритою текою
 * виглядала б як місце поруч із текою, а клала б усередину чи ні — невидимо.
 * Під фільтром перша дитина може бути приховано, тому там лишається «після».
 * Чиста функція: жест у DOM її лише викликає.
 */
export function dropZone({ y, top, height, kind, expanded, hasKids, filtering }) {
  const holds = kind !== "state";
  const r = height > 0 ? (y - top) / height : 0;
  if (!holds) return r < 0.5 ? "before" : "after";
  if (r < 0.25) return "before";
  if (r <= 0.75) return "inside";
  return expanded && hasKids && !filtering ? "first" : "after";
}

/**
 * Чи кидок узагалі йде на сервер. План порахований на дереві ітерації, де
 * почався жест; якщо за цей час `picked` змінився, ті id/index належать
 * іншому дереву — мовчки скасовуємо. Скасований жест, помилка й no-op теж без запиту.
 */
export function shouldCommitDrop({ commit, plan, startIt, currentIt }) {
  if (!commit || !plan || plan.err || plan.noop) return false;
  return startIt === currentIt;
}

/**
 * Куди влучив курсор → зона й ціль (без плану). `hit`: `{kind:"row", id, y, top,
 * height}` | `{kind:"fill"}` | `null`. `state`: `{expanded:Set, filtering, focus}`.
 * Окремо від `resolveDrop`, щоб жест міг дешево порівняти «те саме місце?» і
 * не лічити `planMove` на кожен піксель руху.
 */
export function zoneOfHit(pages, hit, { expanded, filtering = false, focus = null }) {
  if (hit?.kind === "row") {
    const f = flatten(pages).find((x) => x.page.id === hit.id);
    const where = dropZone({
      y: hit.y, top: hit.top, height: hit.height, kind: f?.kind,
      expanded: expanded.has(hit.id), hasKids: !!f?.page.children?.length, filtering,
    });
    return { where, target: hit.id };
  }
  if (hit?.kind === "fill") {
    // у фокусі «кінець» = у кінець гілки, а не кореня
    return focus ? { where: "inside", target: focus } : { where: "end", target: null };
  }
  return { where: null, target: null };
}

/**
 * Повне рішення кидка: зона + `planMove` + що підсвітити.
 *   mark — `{row, cls}`: `row` — id рядка (або null), `cls` — клас; `fill` —
 *   підсвітити порожнє місце. `quiet` — план мовчить (немає цілі, no-op, `self`:
 *   тремтіння над рядком, що тягнуть, не мусить миготіти червоним).
 * Чиста — жест викликає її і при русі, і при відпусканні (план лічиться з
 * ТОЧКИ ВІДПУСКАННЯ, а не з кешу: перемальовка чи прокрутка могли зрушити рядки).
 */
export function resolveDrop(pages, ids, hit, state) {
  const { where, target } = zoneOfHit(pages, hit, state);
  const none = { where, target, plan: null, mark: { row: null, cls: null }, fill: false, quiet: true };
  if (!where) return none;
  const plan = planMove(pages, ids, target, where);
  if (plan.noop || (plan.err === "self")) return { ...none, plan };
  if (plan.err) return { ...none, plan, quiet: false, mark: { row: target, cls: "row--nope" } };
  let mark = { row: null, cls: null };
  let fill = false;
  if (hit?.kind === "fill") fill = true;
  else if (where === "inside") mark = { row: target, cls: "row--in" };
  else if (where === "first") {
    const kid = flatten(pages).find((x) => x.page.id === target)?.page.children?.[0];
    mark = { row: kid ? kid.id : null, cls: "row--drop-before" };
  } else mark = { row: target, cls: where === "before" ? "row--drop-before" : "row--drop-after" };
  return { where, target, plan, mark, fill, quiet: false };
}

/**
 * Чи оновлювати панель з диска, коли дизайнер повертається у вкладку (Клод чи
 * `bin/pages.py` могли змінити `pages.json`, поки вкладка була в тіні).
 *
 * Викликається ДВІЧІ з одним набором ознак: ДО запиту (`rev` не передано —
 * лише «чи тихо») і ПІСЛЯ нього (`rev` — що прийшло, `seenRev` — що бачить
 * панель). Другий виклик обовʼязковий: за час запиту могли почати жест,
 * відкрити діалог, запустити запис чи перемкнути ітерацію, і замінити дерево
 * під рукою — значить зламати дію посеред. Однаковий rev — нічого не
 * робимо (панель не перемальовується даремно, фокус рядка не скидається).
 *   it      — ітерація на старті запиту; current — обрана зараз;
 *   busy    — замок запитів дерева; dragging — триває жест; askOpen — діалог.
 * rev, що не рядок (null з зіпсованої відповіді), оновленням не вважається.
 */
export function shouldRefreshPanel({ it, current, busy = false, dragging = false,
  askOpen = false, rev = undefined, seenRev = undefined }) {
  if (!current || it !== current) return false;
  if (busy || dragging || askOpen) return false;
  if (rev === undefined) return true;
  return typeof rev === "string" && rev !== seenRev;
}

/**
 * Теки, які були в дереві панелі й зникли з нового (fb-01102026-71980b) —
 * лише коли дерево змінив НЕ цей таб. Свої дії над деревом (`treePostNow`)
 * пишуть rev відповіді в `panelRev` ДО перечитування, тож «той самий rev» =
 * наша ж зміна (розгрупували, видалили). Перше читання (`prevRev` порожній) —
 * порівнювати нема з чим. `prevIt` — для якої ітерації було `prev`: дерево
 * ІНШОЇ ітерації (перемикання) — не перезапис, а інший світ. Повертає
 * [{id, name}] у порядку дерева.
 */
export function vanishedFolders({ prev, next, prevRev, nextRev, prevIt, it }) {
  if (!prevRev || nextRev === prevRev || prevIt !== it) return [];
  const have = new Set(flatten(next).filter((f) => f.kind === "folder").map((f) => f.page.id));
  return flatten(prev)
    .filter((f) => f.kind === "folder" && !have.has(f.page.id))
    .map((f) => ({ id: f.page.id, name: f.page.name || f.page.id }));
}
