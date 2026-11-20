/**
 * Розмітка екрана «Підключення» (Deai 0.5.0, етап 3a). Чисті будівельники рядків — як `tasks-home.js`: ні DOM, ні
 * fetch. Логіка (що показати) — у `connections-model.js`; тут лише «стан → HTML» і слова (`t()`).
 *
 *   connPageHTML(v)  v = {space, list, notes, failed, busy}
 *                     space  — запис `/api/spaces` поточного простору ({id, name, path, capabilities});
 *                     list   — записи `GET /api/modules` або `null` (вантажиться);
 *                     notes  — примітки своїх модулів (`GET /api/modules`, `[{folder, code}]`), може не бути;
 *                     failed — `{code, message}`, коли список не прочитався;
 *                     busy   — Map id → 'check'|'disable'|'save': дія в польоті (`'save'` — запис із панелі).
 *                     sec    — розділ «Налаштувань»; ask — `{id}` картки з питанням «Вимкнути?» (етап Е).
 *   mcardHTML(e, busy, ask, space)  картка модуля в сітці розділу «Модулі» (`modules-grid.js`: одна дія + «⋯»; питання в картці);
 *   emptyCardHTML(r) пунктирна картка ролі без модуля; connMenuHTML(e)  меню «⋯» картки (`#th-menu`, як у картки задачі).
 *   drawerHTML(d)    d = {entry, mode: 'enable'|'edit', fields, form, busy: 'save'|'check'|false, result, errors, spaceName};
 *                     busy   — `'save'` (запис: «Зберігаю й перевіряю…»), `'check'` («Перевірити» каже «Перевіряю…»)
 *                              або `false`; будь-яке справжнє значення вимикає всі поля й кнопки (крім хрестика).
 *                     errors — обʼєкт «ключ поля → ключ словника»; читається лише ВЛАСНА властивість (див. `own`).
 *
 * Гачки для `app.js`: `data-cn="<дія>" data-id="<модуль>"` на картках (`card`, `menu`, дія стану, `askno`/`askyes`), `data-cn="cat" [data-role]` у «Додати» і в помилці сторінки, `data-cn-dr="<дія>"` у
 * панелі, `data-cn-field="<ключ>" data-type="<тип>"` на полях.
 *
 * Спільне з майстром 3b (`wizard-view.js`): `fieldHTML` (з префіксом id), `resultHTML`, `badgeHTML`, `rolesLine`, `whyHTML` —
 * майстер малює ті самі поля, бейдж, причину збою й результат запису, що й бічна панель, щоб вони не розійшлись.
 *
 * ⛔ Усе з даних (назви, підписи, опції, тека, `error`, `detail`, id) — лише через `esc()`. ⛔ Значення секрету НІКОЛИ
 * не потрапляє в розмітку: поле пароля завжди порожнє (навіть коли `d.form.secrets` несе щойно введене — форма
 * тримає його для запиту, а не для малювання).
 *
 * ⛔ Ключ поля, роль і id модуля — ДАНІ (з маніфесту): ними не індексують звичайний обʼєкт без `own()`. Ключ
 * `constructor`/`toString` інакше дістав би з прототипа функцію, і `t(err)` кинув би на першому ж рендері; ключ
 * `__proto__` — власна властивість обʼєкта, створеного `Object.fromEntries`/`JSON.parse`, і має читатись як така.
 */
import { esc } from "./esc.js";
import { ico } from "./icons.js";
import { t } from "./i18n.js";
import { navItems, readSec, trustWaitingOf } from "./settings-model.js";
import { agentsActsHTML, agentsBodyHTML } from "./agents-view.js";
import { spaceBodyHTML } from "./space-view.js";
import { generalBodyHTML, keysBodyHTML, updateBodyHTML } from "./app-settings-view.js";
import { confirmHTML } from "./inline-confirm.js";
import { BADGE_CLASS, cardModel, emptyRoles, failedRole, gridEntries, sentence, toolCardModel, toolCards } from "./modules-grid.js";
import { spaceColorToken } from "./spaces-model.js";
import {
  DETAIL_MAX, builtinText, canErase, cardView, disableConsequences, isOwn, noteView, roleIcon, roleKeys, spaceJsonBad, trustLine, whyOf,
} from "./connections-model.js";

/** Назва модуля: вбудований — мовою інтерфейсу, інший — `name` маніфесту як є. */
export const modName = (e) => {
  const k = builtinText(e?.id)?.name;
  return k ? t(k) : String(e?.name || e?.id || "");
};

/** Назва ролі: своя — зі словника; чужа — сам id; порожня — «Інше». */
export const roleTitle = (role) => {
  const k = roleKeys(role);
  return k ? t(k.title) : (role ? String(role) : t("cnRoleOther"));
};

/** Власна властивість `k` обʼєкта `o` (а не прототипна): єдиний дозволений спосіб читати за ключем з даних. */
const own = (o, k) => o != null && typeof k === "string" && Object.prototype.hasOwnProperty.call(o, k);

/* Підпис поля: вбудований модуль — зі словника (мовою інтерфейсу), інший — `label` маніфесту. */
const fieldLabel = (e, f) => {
  const fields = builtinText(e?.id)?.fields;
  const k = own(fields, f.key) ? fields[f.key] : null;
  return k ? t(k) : f.label;
};

export const rolesLine = (e) => (Array.isArray(e?.roles) ? e.roles : []).map(roleTitle).join(" · ");

const BADGES = {
  ok: ["cnBadgeOk", "check"], error: ["cnBadgeError", "warn"], unchecked: ["cnBadgeUnchecked", null],
  off: ["cnBadgeOff", null], missing: ["cnBadgeMissing", "warn"], untrusted: ["cnBadgeUntrusted", "lock"],
};
export const badgeHTML = (kind) => {
  const [key, icon] = BADGES[kind];
  return `<span class="cn-badge cn-badge--${kind}">${icon ? ico(icon, 13) : ""}${esc(t(key))}</span>`;
};

const detailHTML = (d) => (d ? `<span class="cn-why-detail">${esc(d)}</span>` : "");

export function whyHTML(e) {
  const w = whyOf(e);
  if (!w) return "";
  return `<div class="cn-why">${ico("warn", 13)}<span>${esc(t(w.key))}${detailHTML(w.detail)}</span></div>`;
}

/** Пігулка «свій» (свій модуль простору; підказка — його тека в просторі). */
export const ownTagHTML = (e, cls = "cn-tag cn-tag--own") => (isOwn(e)
  ? `<span class="${cls}" title="${esc(String(e.source || ""))}">${esc(t("cnCustom"))}</span>` : "");

/** Текст рядка довіри (`trustLine` моделі) мовою інтерфейсу або `""`. Спільний з кроком 2 майстра. */
export function trustLineText(e) {
  const l = trustLine(e);
  return l ? (l.why ? t(l.key, t(l.why)) : t(l.key)) : "";
}

/** Рядок довіри під описом картки або `""`. */
export function trustLineHTML(e) {
  const s = trustLineText(e);
  return s ? `<p class="cn-trust">${ico("lock", 13)}<span>${esc(s)}</span></p>` : "";
}

/* Дія картки → [ключ підпису, іконка]. Імена дій — гачки `data-cn` для `app.js`; на картці модуля стоїть рівно одна. */
const MC_ACTIONS = {
  enable: ["cnEnable", "plus"], configure: ["cnConfigure", "pencil"], check: ["cnCheck", "refresh"],
  trust: ["cnTrust", "lock"], trustinfo: ["cnTrustInfo", "help"],
};

/** Питання «Вимкнути?» у картці: назва + наслідки для ролей, які модуль зараз виконує (`disableConsequences`). */
function askTitle(e, space) {
  const lines = disableConsequences(e, space).map((c) =>
    (c.consKey ? t(c.consKey) : t("cnDisableNone", roleTitle(c.role), c.noneKey ? t(c.noneKey) : "")));
  return [t("cnDisableAsk", modName(e)), ...lines].join(" ");
}

/**
 * Картка модуля в сітці. `busy` — Map id → дія в польоті (кнопка вимкнена, «Перевірити» каже «Перевіряю…»); `ask` — `{id}`
 * картки, що питає «Вимкнути?» (питання на місці бейджа й дії; «⋯» і клік по картці тоді нема). `space` — для наслідків питання.
 */
export function mcardHTML(e, busy, ask, space) {
  const id = esc(e.id);
  const name = modName(e);
  const ic = ico(isOwn(e) ? "puzzle" : roleIcon(e.roles?.[0]), 18);
  const roles = rolesLine(e);
  /* Назва картки — справжня кнопка (`.mc-open`), яку CSS розтягує на всю картку (`::after`): картка клікається мишею, а для
     клавіатури й читача це ОДНА кнопка, а не `role=button` із вкладеними кнопками (⋯, дія). Картка без дії на клік — звичайний текст. */
  const top = (more, open) => `<div class="mc-top"><span class="mc-ic">${ic}</span><div class="mc-name">`
    + `<b>${open ? `<button type="button" class="mc-open" data-cn="card" data-id="${id}">${esc(name)}</button>` : esc(name)}${ownTagHTML(e, "mc-tag")}</b>`
    + `${roles ? `<span>${esc(roles)}</span>` : ""}</div>${more}</div>`;
  if (ask && ask.id === e.id) {
    return `<div class="mc mc--ask" role="group" aria-label="${esc(name)}" data-id="${id}">${top("", false)}${confirmHTML({
      title: askTitle(e, space), no: t("askCancel"), yes: t("cnDisable"),
      noAttrs: `data-cn="askno" data-id="${id}"`, yesAttrs: `data-cn="askyes" data-id="${id}"`,
    })}</div>`;
  }
  const failed = failedRole(e, space?.capabilities) !== "";
  const m = cardModel(e, failed);
  const b = busy?.get?.(e.id) ?? null;
  const more = `<button type="button" class="mc-more" data-cn="menu" data-id="${id}" aria-haspopup="menu" aria-expanded="false"`
    + ` aria-label="${esc(t("mcMore", name))}" title="${esc(t("mcMore", name))}">${ico("dots")}</button>`;
  const w = cardView(e).why ? whyOf(e) : null;   // причина — лише коли її показує й `cardView` (вимкнений зі старою помилкою — без неї)
  /* Збій ролі з `capabilities.errors` (раніше — рядок «Зараз»): причина картки, коли власної (`whyOf`) нема. */
  const line = w ? `${esc(t(w.key))}${w.detail ? ` ${esc(w.detail)}` : ""}` : esc(failed ? t("mcRoleError") : trustLineText(e));
  const why = line ? `<p class="mc-why">${line}</p>` : "";
  const bdgKey = BADGES[m.badge][0];
  const bdg = `<span class="bdg bdg--${BADGE_CLASS[m.badge]}">${m.badge === "untrusted" ? ico("lock", 13) : ""}${esc(t(bdgKey))}</span>`;
  let act = "";
  if (m.action) {
    const [key, icon] = MC_ACTIONS[m.action];
    const label = m.action === "check" && b === "check" ? t("cnChecking") : t(key);
    act = `<button type="button" class="ctl ctl--out" data-cn="${m.action}" data-id="${id}"${b ? " disabled" : ""}>${ico(icon)}${esc(label)}</button>`;
  }
  /* Дія в польоті (`busy`): картка не відповідає на клік (`connAction`), і `aria-busy` каже це читачеві й тестам. */
  return `<div class="mc" data-id="${id}"${b ? ' aria-busy="true"' : ""}>${top(more, m.click !== null)}`
    + `${why}<div class="mc-foot">${bdg}${act}</div></div>`;
}

/**
 * Картка інструмента простору («В Figma», `toolCards` у `modules-grid.js`): та сама оболонка `.mc`, що в модуля, але ім'я — звичайний текст
 * (шухляди нема), а дія — `data-cn="toolon"`; «⋯» веде в `toolask` → питання в картці (`.mc--ask`, `askno`/`askyes` із id картки).
 */
export function toolCardHTML(c, busy, ask) {
  const id = esc(c.id);
  const name = t(c.nameKey);
  const m = toolCardModel(c);
  const top = (more) => `<div class="mc-top"><span class="mc-ic">${ico(c.icon, 18)}</span><div class="mc-name"><b>${esc(name)}</b>`
    + `<span>${esc(t(c.roleKey))}</span></div>${more}</div>`;
  if (ask && ask.id === c.id) {
    return `<div class="mc mc--ask" role="group" aria-label="${esc(name)}" data-id="${id}">${top("")}${confirmHTML({
      title: [t("toolDisableQ", name), t(m.askKey)].join(" "), no: t("askCancel"), yes: t("cnDisable"),
      noAttrs: `data-cn="askno" data-id="${id}"`, yesAttrs: `data-cn="askyes" data-id="${id}"`,
    })}</div>`;
  }
  const b = busy?.get?.(c.id) ?? null;
  const more = m.menu.length
    ? `<button type="button" class="mc-more" data-cn="menu" data-id="${id}" aria-haspopup="menu" aria-expanded="false"`
      + ` aria-label="${esc(t("mcMore", name))}" title="${esc(t("mcMore", name))}">${ico("dots")}</button>` : "";
  const bdg = `<span class="bdg bdg--${BADGE_CLASS[m.badge]}">${esc(t(m.badgeKey))}</span>`;
  const act = m.action
    ? `<button type="button" class="ctl ctl--out" data-cn="${m.action.act}" data-id="${id}"${b ? " disabled" : ""}>${ico("plus")}${esc(t(m.action.key))}</button>` : "";
  return `<div class="mc" data-id="${id}"${b ? ' aria-busy="true"' : ""}>${top(more)}<div class="mc-foot">${bdg}${act}</div></div>`;
}

/** Меню «⋯» картки інструмента: той самий `#th-menu`, пункти — `data-cn` + `data-id` картки. */
export function toolMenuHTML(c) {
  const id = esc(c.id);
  const items = toolCardModel(c).menu.map((i) => `<button type="button" role="menuitem" tabindex="-1"${i.danger ? ' class="danger"' : ""}`
    + ` data-cn="${i.act}" data-id="${id}"><span>${esc(t(i.key))}</span></button>`).join("");
  return `<div id="th-menu" class="cv-ctx th-menu" role="menu" aria-label="${esc(t("mcMore", t(c.nameKey)))}">${items}</div>`;
}

/** Пунктирна картка ролі без модуля: іконка, назва ролі, наслідок («none» ролі) реченням — або збій ролі (`r.error`), «Додати» (каталог). */
export function emptyCardHTML(r) {
  const line = r.error ? t("mcRoleError") : sentence(t(r.noneKey));
  return `<div class="mc mc--empty" data-role="${esc(r.role)}"><div class="mc-top"><span class="mc-ic">${ico(r.icon, 18)}</span>`
    + `<div class="mc-name"><b>${esc(t(r.titleKey))}</b><span>${esc(line)}</span></div></div>`
    + `<div class="mc-foot"><span></span><button type="button" class="ctl ctl--out" data-cn="cat" data-role="${esc(r.role)}">${ico("plus")}${esc(t("mcAddRole"))}</button></div></div>`;
}

/** Меню «⋯» картки: той самий `.cv-ctx`, що й меню картки задачі; пункти — `data-cn` + `data-id` (ловить `wireHome`). */
export function connMenuHTML(e) {
  const id = esc(e.id);
  const items = cardModel(e).menu.map((i) => {
    if (i === "sep") return '<hr role="separator">';
    return `<button type="button" role="menuitem" tabindex="-1"${i.danger ? ' class="danger"' : ""} data-cn="${i.act}" data-id="${id}">`
      + `<span>${esc(t(i.key))}</span></button>`;
  }).join("");
  return `<div id="th-menu" class="cv-ctx th-menu" role="menu" aria-label="${esc(t("mcMore", modName(e)))}">${items}</div>`;
}

/** Сітка розділу «Модулі»: картки (увімкнені, свої, «Не встановлено») + «Без модуля · N». */
function gridHTML(v) {
  const cards = gridEntries(v.list).map((e) => mcardHTML(e, v.busy, v.ask, v.space)).join("")
    + toolCards(v.tools).map((c) => toolCardHTML(c, v.busy, v.ask)).join("");
  const empty = emptyRoles(v.list, v.space?.capabilities);
  return `${cards ? `<div class="mg">${cards}</div>` : ""}`
    + (empty.length ? `<h2 class="sub">${esc(t("mcEmptyH", empty.length))}</h2><div class="mg">${empty.map(emptyCardHTML).join("")}</div>` : "");
}

/** Примітки своїх модулів (`notes` відповіді) рядками під головою; нема — `""`. */
function notesHTML(notes) {
  const list = noteView(notes);
  if (!list.length) return "";
  return `<ul class="cn-notes">${list.map((n) => `<li class="cn-note">${ico("warn", 13)}`
    + `<span>${esc(t(n.key, n.folder))}</span></li>`).join("")}</ul>`;
}

/** Ліва навігація «Налаштувань»: групи «Простір · {імʼя}» і «Застосунок»; поточний розділ — `aria-current`. */
function setNavHTML(sp, sec, list, agentsOutdated = false) {
  const items = navItems({ trustWaiting: trustWaitingOf(list), agentsOutdated });
  const dot = `<span class="space-dot" style="background:var(--${spaceColorToken(sp.color)})"></span>`;
  const head = { space: `<h6>${dot}${esc(t("setNavSpace", sp.name))}</h6>`, app: `<h6>${esc(t("setNavApp"))}</h6>` };
  let out = "";
  let group = "";
  for (const it of items) {
    if (it.group !== group) { group = it.group; out += head[group]; }
    const cur = it.id === sec ? ' aria-current="page"' : "";
    const bdg = !it.badge ? ""
      : it.badge.kind === "count" ? `<span class="set-cnt" title="${esc(t("setTrustWaiting"))}">${it.badge.n}</span>`
      : `<span class="set-dotb" title="${esc(t("setAgentsOutdated"))}"></span>`;
    out += `<button class="nav-i" data-th="csec" data-v="${it.id}"${cur}>${ico(it.icon)}<span>${esc(t(it.labelKey))}</span>${bdg}</button>`;
  }
  return `<nav class="set-nav" aria-label="${esc(t("settings"))}">${out}</nav>`;
}

/** Сторінка «Налаштування»: ліва навігація + вміст розділу `v.sec`. Простору нема — порожньо (входів тоді нема, `app.js` сюди не пускає). */
export function connPageHTML(v) {
  const sp = v?.space;
  if (!sp) return "";
  const sec = readSec(v.sec);
  const h1 = `<h1 class="th-h" id="cn-title">${esc(t(navItems().find((x) => x.id === sec).labelKey))}</h1>`;
  /* Розділ «Модулі»: у голові праворуч «Додати модуль» (лише коли список прочитано — є що додавати). */
  const addBtn = `<button type="button" class="ctl ctl--out" data-cn="cat">${ico("plus")}${esc(t("mcAdd"))}</button>`;
  const wrap = (inner, head = "") => `<div class="set">${setNavHTML(sp, sec, v.list, v.agents?.outdated === true)}<div class="set-main"><div class="set-in cn-in">${head ? `<div class="th-head">${h1}${head}</div>` : h1}${inner}</div></div></div>`;
  if (sec === "space") return wrap(spaceBodyHTML(sp));
  if (sec === "agents") return wrap(agentsBodyHTML(v.agents, v.agentsBusy === true), agentsActsHTML(v.agents, v.agentsBusy === true));
  if (sec === "app") return wrap(generalBodyHTML(v.general));
  if (sec === "upd") return wrap(updateBodyHTML(v.update, v.updChecking === true));
  if (sec === "keys") return wrap(keysBodyHTML());
  if (sec !== "mods") return wrap("");
  /* space.json не читається — двома шляхами: сервер сказав `capabilities.error === "space-json-unreadable"` або відмовив
     списку модулів (`409 space-json-unreadable`). В обох випадках решта `capabilities` нічого не варта, картки не малюємо.
     Збій МОДУЛЯ ролі (інший код `error`) сюди не потрапляє: він іде в рядок «Зараз» своєї ролі, решта карток живі (r15-1). */
  const sjBad = spaceJsonBad(sp.capabilities) || v.failed?.code === "space-json-unreadable";
  if (sjBad || v.failed) {
    const msg = sjBad ? t("cnErrSpaceJson", sp.path || "") : t("cnErrLoad");
    const det = !sjBad && v.failed?.message ? detailHTML(String(v.failed.message).slice(0, DETAIL_MAX)) : "";
    return wrap(`<div class="cn-err" role="alert">${ico("warn")}<span>${esc(msg)}${det}</span>`
      + `<button class="ctl ctl--out" data-cn="retry">${ico("refresh")}${esc(t("retry"))}</button></div>`);
  }
  if (!Array.isArray(v.list)) return wrap(`<p class="cn-loading" role="status">${esc(t("cnLoading"))}</p>`);
  return wrap(`${notesHTML(v.notes)}${gridHTML(v)}`, addBtn);
}

/* Стан секрету за `set` (`true|false|null`) → ключ словника. Не таблицею з ключами «true»/«null»: `set` — поле даних. */
const secretStateKey = (set) => (set === true ? "cnSecretSet" : set === false ? "cnSecretUnset" : "cnSecretUnknown");

/** ` aria-describedby="…"` з id через пробіл; порожні (`""`, `false`) відкидаються; усі порожні — атрибута нема. */
const describedBy = (...ids) => {
  const list = ids.filter((x) => typeof x === "string" && x);
  return list.length ? ` aria-describedby="${list.join(" ")}"` : "";
};
/*
 * Поле форми. Звʼязки для читача екрана: `<label for>` ↔ `id`; обовʼязкове — `aria-required`; помилка — `aria-invalid`
 * + `aria-describedby` на її `<p id>`; підказка шляху, рядок стану секрету й примітка стирання теж описують поле —
 * ідентифікатори похідні від `cn-f-<i>` (`-hint`, `-state`, `-erase`, `-err`) і ідуть в одному атрибуті через пробіл.
 * `prefix` — голова id полів: панель 3a — `cn-f` (типово), майстер — `wz-f-<картка>` (кілька карток на сторінці, id не
 * мусять збігатися); похідні id (`-hint`, `-state`, …) наслідують її.
 *
 * ⚠️ Примітку стирання (`-erase`) у `aria-describedby` кладемо лише коли секрет ПОЗНАЧЕНО до стирання: елемент із
 * `hidden`, на який указує `aria-describedby`, усе одно озвучується — «буде стерто після збереження» звучало б при
 * кожному непозначеному секреті. Хто перемикає позначку без перемальовки (`toggleCnErase`), мусить так само
 * додати/зняти цей id в атрибуті поля.
 */
export function fieldHTML(e, f, i, d, prefix = "cn-f") {
  const id = `${prefix}-${i}`;
  /* Ключ словника помилки; невідомий ключ кине в `t()` на першому ж рендері — так і задумано (як скрізь в `i18n.js`). */
  const err = own(d.errors, f.key) ? d.errors[f.key] : "";
  const errId = err ? `${id}-err` : "";
  const inv = err ? ' aria-invalid="true"' : "";
  const dis = d.busy ? " disabled" : "";
  const data = `data-cn-field="${esc(f.key)}" data-type="${esc(f.type)}"`;
  const reqMark = f.required ? ' <span class="cn-req" aria-hidden="true">*</span>' : "";
  /* `aria-required` — лише полям з рядковим значенням: прапорець (`bool`) його не отримує, «обовʼязкового прапорця» нема. */
  const req = f.required ? ' aria-required="true"' : "";
  const label = `${esc(fieldLabel(e, f))}${reqMark}`;
  const errHTML = err ? `<p class="cn-field-err" id="${errId}">${esc(t(err))}</p>` : "";
  const val = own(d.form?.values, f.key) ? d.form.values[f.key] : "";
  if (f.type === "bool") {
    return `<div class="cn-field"><label class="cn-check"><input type="checkbox" id="${id}" ${data}`
      + `${val === true ? " checked" : ""}${inv}${describedBy(errId)}${dis}> ${label}</label>${errHTML}</div>`;
  }
  let ctl;
  if (f.type === "select") {
    /* Порожній варіант — за `f.blank` моделі, а не за `!f.required`: обовʼязковому без дійсного значення він теж
       потрібен (інакше браузер мовчки обрав би перший варіант, і форма записала б його, хоча людина нічого не
       обирала), а обовʼязковому з дійсним — шкідливий (дозволив би «очистити» обовʼязкове). Вибрана вона, коли
       значення форми порожнє — так само, як стартує `initialForm`. */
    const blank = f.blank ? `<option value=""${val === "" ? " selected" : ""}>—</option>` : "";
    const opts = blank + (f.options ?? []).map((o) =>
      `<option value="${esc(o.value)}"${o.value === val ? " selected" : ""}>${esc(o.label)}</option>`).join("");
    ctl = `<select class="cn-inp" id="${id}" ${data}${req}${inv}${describedBy(errId)}${dis}>${opts}</select>`;
  } else if (f.type === "secret") {
    const erase = Array.isArray(d.form?.erase) && d.form.erase.includes(f.key);
    /* «Стерти» — рівно та сама перевірка, що в патчі моделі: кнопка, яку патч однаково проігнорував би, не малюється. */
    const erasable = canErase(f);
    const stateId = `${id}-state`;
    const eraseId = `${id}-erase`;
    /* ⛔ Жодного `value` на полі пароля — ні `f.value`, ні `d.form.secrets[f.key]`. */
    ctl = `<div class="cn-secret-row"><input class="cn-inp" type="password" id="${id}" ${data}`
      + ` autocomplete="new-password" spellcheck="false"`
      + ` placeholder="${esc(t(f.set === true ? "cnSecretKeep" : "cnSecretEnter"))}"${req}${inv}`
      + `${describedBy(stateId, erasable && erase && eraseId, errId)}${dis}>`
      /* Підпис СТАЛИЙ, стан — `aria-pressed` + видима примітка; доступне імʼя називає поле (їх на панелі кілька). */
      + `${erasable ? `<button type="button" class="ctl" data-cn-dr="erase" data-key="${esc(f.key)}" aria-pressed="${erase}"`
        + ` aria-label="${esc(t("cnEraseFor", fieldLabel(e, f)))}"${dis}>${esc(t("cnErase"))}</button>` : ""}</div>`
      + `<p class="cn-secret" id="${stateId}">${ico("lock", 13)}<span>${esc(t(secretStateKey(f.set)))} · ${esc(t("cnSecretWhere"))}</span></p>`
      + (erasable ? `<p class="cn-hint" id="${eraseId}" data-cn-erase-note="${esc(f.key)}"${erase ? "" : " hidden"}>${esc(t("cnEraseMarked"))}</p>` : "");
  } else {
    const hintId = f.type === "path" ? `${id}-hint` : "";
    ctl = `<input class="cn-inp" type="text" id="${id}" ${data} value="${esc(val)}" spellcheck="false" autocomplete="off"`
      + `${req}${inv}${describedBy(hintId, errId)}${dis}>`
      + (hintId ? `<p class="cn-hint" id="${hintId}">${esc(t("cnPathHint"))}</p>` : "");
  }
  return `<div class="cn-field"><label class="cn-lbl" for="${id}">${label}</label>${ctl}${errHTML}</div>`;
}

export function resultHTML(r) {
  if (!r) return "";
  if (r.kind === "ok") {
    return `<div class="cn-res cn-res--ok" role="status">${ico("check", 13)}<span>${esc(t(r.key))}${detailHTML(r.detail)}</span></div>`;
  }
  const head = r.kind === "failed" ? `<b>${esc(t("cnSavedButFailed"))}</b> ` : "";
  /* Після «Збережено, але перевірка не пройшла.» загальне «Перевірка не пройшла.» — повтор голови: лишаємо голову й
     деталь. Конкретний код (свій текст) і інші види (там голови нема) текст ключа зберігають. */
  const text = r.kind === "failed" && r.key === "cnErrGeneric" ? "" : esc(t(r.key));
  return `<div class="cn-res cn-res--err" role="alert">${ico("warn", 13)}<span>${head}${text}${detailHTML(r.detail)}</span></div>`;
}

/**
 * Бічна панель. `result.kind`: `ok` (зелений), `failed` (збережено, але перевірка не пройшла), `check-failed`
 * (кнопка «Перевірити» в панелі сказала «ні»), `refused` (HTTP-відмова — нічого не збережено).
 */
export function drawerHTML(d) {
  const e = d.entry;
  const desc = builtinText(e?.id)?.desc;
  const body = d.fields.length ? d.fields.map((f, i) => fieldHTML(e, f, i, d)).join("")
    : `<p class="cn-dr-none">${esc(t("cnNoSettings"))}</p>`;
  /* Два види зайнятості: «запис» каже «Зберігаю й перевіряю…» на головній кнопці, «перевірка» — «Перевіряю…» на
     «Перевірити»; решта вимкнена в обох. */
  const primary = d.busy === "save" ? t("cnBusy") : t(d.mode === "enable" ? "cnEnable" : "cnSave");
  const checkLabel = d.busy === "check" ? t("cnChecking") : t("cnCheck");
  return `<form class="cn-dr-form" novalidate>
    <div class="cn-dr-head"><span class="cn-ic">${ico(roleIcon(e?.roles?.[0]))}</span>
      <div class="cn-dr-name"><b id="cn-dr-title">${esc(modName(e))}</b>`
    + `<span class="cn-card-role">${esc([rolesLine(e), d.spaceName].filter(Boolean).join(" · "))}</span></div>
      <button type="button" class="ctl ctl--icon" data-cn-dr="close" aria-label="${esc(t("cnClose"))}" title="${esc(t("cnClose"))}">${ico("x")}</button></div>
    <div class="cn-dr-body">${desc ? `<p class="cn-card-desc">${esc(t(desc))}</p>` : ""}${body}${resultHTML(d.result)}</div>
    <div class="cn-dr-foot">${isOwn(e) && e.record === true
      ? `<button type="button" class="ctl ctl--out cn-dr-untrust" data-cn-dr="untrust"${d.busy ? " disabled" : ""}>${ico("trash")}${esc(t("cnUntrust"))}</button>` : ""}${d.mode === "edit"
      ? `<button type="button" class="ctl ctl--out" data-cn-dr="check"${d.busy ? " disabled" : ""}>${ico("refresh")}${esc(checkLabel)}</button>` : ""}
      <span class="cn-grow"></span>
      <button type="submit" class="ctl ctl--pri" data-cn-dr="submit"${d.busy ? " disabled" : ""}>${esc(primary)}</button></div></form>`;
}
