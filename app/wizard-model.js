/**
 * Модель майстра нового простору (Deai 0.6.0, етап 3b; спека
 * `docs/superpowers/specs/2026-10-21-first-run-wizard-design.md`). Чисті функції: ні DOM, ні fetch, ні `t()` — як
 * `connections-model.js`, на якій вона стоїть. Вхід — записи `GET /api/modules` (`{id, roles, enabled, implicit,
 * status, settings[]}`).
 *
 * Вибір кроку 2 — МНОЖИНА id модулів (`pick`), радіокнопки лише її показують: модуль кількох ролей стоїть у секції
 * кожної своєї ролі, і вибрати його = прибрати з `pick` усіх, хто ділить із ним хоч одну роль.
 *
 * ⛔ Ролі — ДАНІ (з маніфестів): мапи ролей — лише `Map` (роль `__proto__` — звичайний ключ, а не прототип).
 */
import { ROLE_ORDER, formPatch, isDirty } from "./connections-model.js";

/** Кроки майстра — у порядку спеки; номер кроку = індекс + 1. */
export const WZ_STEPS = ["space", "modules", "settings", "task"];

const list0 = (list) => (Array.isArray(list) ? list : []);
const rolesOf = (e) => [...new Set(Array.isArray(e?.roles) ? e.roles.filter((r) => typeof r === "string" && r) : [])];
/* Запис, з яким майстер працює: обʼєкт з id і не `missing` (тим місце в «Підключенні»). */
const valid = (e) => !!e && typeof e === "object" && typeof e.id === "string" && !!e.id && e.status !== "missing";
/* Тримає роль: увімкнений (зокрема неявно). Зламаний (`status: error`) теж тримає — як `roleHolders` у 3a. */
const holds = (e) => valid(e) && e.enabled === true;
const entryOf = (list, id) => list0(list).find((e) => valid(e) && e.id === id) ?? null;

/** Секції кроку 2: `[{role, modules}]` — ролі `ROLE_ORDER`, далі інші за абеткою; модуль кількох ролей — у КОЖНІЙ. */
export function wizardSections(list) {
  const byRole = new Map();
  for (const e of list0(list)) {
    if (!valid(e)) continue;
    for (const r of rolesOf(e)) {
      if (!byRole.has(r)) byRole.set(r, []);
      byRole.get(r).push(e);
    }
  }
  const named = [...byRole.keys()].filter((r) => !ROLE_ORDER.includes(r)).sort();
  return [...ROLE_ORDER.filter((r) => byRole.has(r)), ...named].map((role) => ({ role, modules: byRole.get(role) }));
}

/** Хто зараз тримає кожну роль: `Map<роль, id[]>`, id відсортовані. Знімок кроку 2 — основа «свіжості». */
export function holdersByRole(list) {
  const out = new Map();
  for (const e of list0(list)) {
    if (!holds(e)) continue;
    for (const r of rolesOf(e)) {
      if (!out.has(r)) out.set(r, []);
      out.get(r).push(e.id);
    }
  }
  for (const v of out.values()) v.sort();
  return out;
}

/** Початковий вибір: усі, хто зараз тримає хоч одну роль. */
export const initialPick = (list) => new Set(list0(list).filter((e) => holds(e) && rolesOf(e).length).map((e) => e.id));

/** Вибрати модуль: прибрати з вибору кожен інший, що ділить із ним роль (і ті, кого вже нема в списку). */
export function pickModule(pick, list, id) {
  const e = entryOf(list, id);
  if (!e) return new Set(pick);
  const mine = new Set(rolesOf(e));
  const out = new Set([...pick].filter((x) => {
    const o = entryOf(list, x);
    return !!o && !rolesOf(o).some((r) => mine.has(r) && x !== id);
  }));
  out.add(id);
  return out;
}

/** «Без модуля» в ролі: прибрати з вибору всіх, хто її тримає. */
export const pickNone = (pick, list, role) =>
  new Set([...pick].filter((x) => { const o = entryOf(list, x); return !!o && !rolesOf(o).includes(role); }));

/** Вибраний постачальник ролі (перший за порядком списку) або `null` — «Без модуля». */
export const pickedFor = (pick, list, role) =>
  list0(list).find((e) => valid(e) && pick.has(e.id) && rolesOf(e).includes(role))?.id ?? null;

/** Вибрані модулі в порядку секцій; модуль кількох ролей — один раз, на першій. */
export function pickedInOrder(list, pick) {
  const seen = new Set();
  const out = [];
  for (const s of wizardSections(list)) {
    for (const e of s.modules) {
      if (pick.has(e.id) && !seen.has(e.id)) { seen.add(e.id); out.push(e); }
    }
  }
  return out;
}

/** Рядки «Без модуля» кроку 3: ролі без вибраного постачальника, які хтось тримає, → `[{role, holder}]`. */
export function offRows(list, pick) {
  const out = [];
  for (const s of wizardSections(list)) {
    if (pickedFor(pick, list, s.role)) continue;
    for (const e of s.modules) if (holds(e)) out.push({ role: s.role, holder: e });
  }
  return out;
}

/**
 * Errored-тримачі, яких `replace` НЕ вимкне, але які мусять піти разом із заміною (`freed` — ролі, що їх звільняють
 * enable-и), у порядку секцій, раз на тримача (на першій звільненій ролі): тримач (`holds`) зі `status: error` (сервер
 * `deai_modules._holders` рахує тримачами лише завантажені модулі), не вибраний людиною і без власного рядка в `offRows`.
 * Спільне для `errOffRows` (що показує вʼю) і `writePlan` (що шле контролер) — щоб вони не розійшлись.
 */
function erroredOfFreed(list, pick, freed) {
  const listed = new Set(offRows(list, pick).map((o) => o.holder.id));
  const out = [];
  for (const s of wizardSections(list)) {
    if (!freed.has(s.role)) continue;
    for (const e of s.modules) {
      if (!holds(e) || e.status !== "error" || pick.has(e.id) || listed.has(e.id)) continue;
      listed.add(e.id);
      out.push({ role: s.role, holder: e });
    }
  }
  return out;
}

/**
 * Рядки «буде вимкнено» кроку 3 для errored-тримачів ролі, яку замінить вибраний ще не ввімкнений модуль: `[{role, holder}]`
 * (`offRows` їх не знає — роль має вибраного). Рівно ті, кому `writePlan` дасть окремий `disable`, коли нічого не застаріло
 * (`stale` рахує лише `writePlan`) і нічого не зникло (`gone`): без цих рядків людина не бачила б, що вимкнеться, а збій
 * їхнього `disable` лишив би `allOk` хибним, а картку — без видимої причини.
 */
export const errOffRows = (list, pick) =>
  erroredOfFreed(list, pick, new Set(pickedInOrder(list, pick).filter((e) => e.enabled !== true).flatMap(rolesOf)));

const sameIds = (a, b) => a.length === b.length && a.every((x, i) => x === b[i]);

/** Ролі, тримачі яких зараз (`fresh`) не ті, що бачив крок 2 (`atPick`): запис у такій ролі не шлемо. */
export const staleRoles = (roles, atPick, fresh) =>
  roles.filter((r) => !sameIds(atPick?.get?.(r) ?? [], fresh?.get?.(r) ?? []));

/**
 * План записів кроку 3 зі СВІЖОГО списку: `[{op, id, roles, stale}]`. Порядок:
 *   gone     — вибраний, якого вже нема у свіжому списку (писати нема що; картка скаже чому): ПЕРШИМИ;
 *   enable / settings — далі У ПОРЯДКУ СЕКЦІЙ, по одному («по черзі», як хоче спека), а не «усі enable, потім усі settings»:
 *              enable — вибраний, ще не ввімкнений (контролер шле `replace: true` — згода дана вибором на кроці 2);
 *              settings — вибраний, увімкнений, форма змінена (`formPatch` → `isDirty`); без форми чи без змін — нічого;
 *   disable  — ОСТАННІМИ: тримач ролі з «Без модуля», якого не вимикає жоден `enable` (заміна вимикає тримачів УСІХ ролей
 *              нового модуля, тож тримач кількох ролей міг піти разом із заміною в іншій ролі), і errored-тримач звільненої ролі.
 * `forms` — `Map<id, {fields, init, cur}>`; `atPick` — `holdersByRole` списку, який бачила людина на кроці 2;
 * `prevList` — сам той список кроку 2: з нього `gone` бере ролі зниклого модуля (свіжий список його вже не має).
 * `stale` — ролі запису, тримачі яких змінились після кроку 2 (для `settings` не рахується: роль не міняється).
 *
 * ⛔ Роль, яку мав зайняти зниклий (`gone`) модуль, не чіпаємо: НІЯКОГО disable для неї (тримач лишається — інакше публікація
 * чи коментарі лишились би без нікого, а людина просила іншого) і для тримача, що має хоч одну таку роль. Ролі зниклого
 * НЕВІДОМІ (його нема й у `prevList`, чи `prevList` не передали) — тоді disable не шлемо взагалі: не знаємо, чию роль він займав.
 *
 * Errored-тримач звільненої ролі (`status: error`; список — `errOffRows`, його ж бачить вʼю): сервер `deai_modules._holders` рахує тримачами лише модулі, що
 * завантажились (`m.status == 'ok'`), тож `replace: true` такого НЕ вимикає, а явний `module-disable` дозволений будь-якому
 * модулю каталогу (звіряно в `write_module_state`). Тому для нього — окремий `disable`, один на тримача. Статус `error` у
 * списку — і «не завантажився», і «остання перевірка впала»: у другому випадку `replace` вимикає сам, і зайвий `disable` після нього
 * безпечний (повторне вимкнення вимкненого — нічого не пише).
 */
export function writePlan({ list, pick, forms, atPick, prevList }) {
  const fresh = holdersByRole(list);
  const ops = [];
  const goneRoles = new Set();
  let goneBlind = false;
  for (const id of pick) {
    if (entryOf(list, id)) continue;
    const was = rolesOf(entryOf(prevList, id));
    if (!was.length) goneBlind = true;
    was.forEach((r) => goneRoles.add(r));
    ops.push({ op: "gone", id, roles: was, stale: [] });
  }
  const freed = new Set();
  for (const e of pickedInOrder(list, pick)) {
    const roles = rolesOf(e);
    if (e.enabled !== true) {
      const stale = staleRoles(roles, atPick, fresh);
      if (!stale.length) roles.forEach((r) => freed.add(r));
      ops.push({ op: "enable", id: e.id, roles, stale });
      continue;
    }
    const f = forms?.get?.(e.id);
    if (f && isDirty(formPatch(f.fields, f.init, f.cur))) ops.push({ op: "settings", id: e.id, roles, stale: [] });
  }
  if (goneBlind) return ops;
  const off = new Set();
  const disable = (holder, role, stale) => {
    if (off.has(holder.id)) return;
    off.add(holder.id);
    ops.push({ op: "disable", id: holder.id, roles: [role], stale });
  };
  /* Тримач, що ділить роль із зниклим, або тримач, якого вже вимкне заміна, — не наш: gone його не чіпає, replace вимкне сам. */
  for (const { role, holder } of offRows(list, pick)) {
    const mine = rolesOf(holder);
    if (mine.some((r) => goneRoles.has(r))) continue;
    if (mine.some((r) => freed.has(r)) && holder.status !== "error") continue;
    disable(holder, role, staleRoles([role], atPick, fresh));
  }
  for (const { role, holder } of erroredOfFreed(list, pick, freed)) {
    if (!rolesOf(holder).some((r) => goneRoles.has(r))) disable(holder, role, []);
  }
  return ops;
}

/** Чи всі результати проходу — успіх (запис прийнято й перевірка `ok`, або вимкнено). Порожньо — так. */
export const allOk = (results) => results.every((r) => r?.kind === "ok");

/** Крок «Назад»: 2→1, 3→2, 4→3; 4→2, коли крок 3 пропущено (модулі не прочитались). */
export const prevStep = (step, skipped3 = false) => (step === 4 && skipped3 ? 2 : Math.max(1, step - 1));

/** Назва задачі з теки-джерела: останній сегмент шляху без хвостових слешів і пробілів, обрізаний; «~», «.», «..» і порожнє — ''. */
export function titleFromFolder(p) {
  const s = String(p ?? "").replace(/[\s\\/]+$/, "");
  const base = (s.split(/[\\/]/).pop() ?? "").trim();
  return base === "~" || base === "." || base === ".." ? "" : base;
}
