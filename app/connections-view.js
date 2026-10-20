/**
 * Розмітка екрана «Підключення» (Deai 0.5.0, етап 3a). Чисті будівельники рядків — як `tasks-home.js`: ні DOM, ні
 * fetch. Логіка (що показати) — у `connections-model.js`; тут лише «стан → HTML» і слова (`t()`).
 *
 *   connPageHTML(v)  v = {space, list, failed, busy}
 *                     space  — запис `/api/spaces` поточного простору ({id, name, path, integrations, capabilities});
 *                     list   — записи `GET /api/modules` або `null` (вантажиться);
 *                     failed — `{code, message}`, коли список не прочитався;
 *                     busy   — Map id → 'check'|'disable': дія в польоті.
 *   cardHTML(e, busy)  одна картка модуля; nowHTML(role, v)  рядок «Зараз» секції.
 *   drawerHTML(d)    d = {entry, mode: 'enable'|'edit', fields, form, busy, result, errors, spaceName};
 *                     busy   — `'save'` (запис: «Зберігаю й перевіряю…»), `'check'` («Перевірити» каже «Перевіряю…»)
 *                              або `false`; будь-яке справжнє значення вимикає всі поля й кнопки (крім хрестика).
 *                     errors — обʼєкт «ключ поля → ключ словника»; читається лише ВЛАСНА властивість (див. `own`).
 *
 * Гачки для `app.js`: `data-cn="<дія>" data-id="<модуль>"` на картках і в помилці сторінки, `data-cn-dr="<дія>"` у
 * панелі, `data-cn-field="<ключ>" data-type="<тип>"` на полях.
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
import {
  DETAIL_MAX, builtinText, canErase, cardView, groupModules, providerLine, roleIcon, roleKeys, whyOf,
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

const rolesLine = (e) => (Array.isArray(e?.roles) ? e.roles : []).map(roleTitle).join(" · ");

const BADGES = {
  ok: ["cnBadgeOk", "check"], error: ["cnBadgeError", "warn"], unchecked: ["cnBadgeUnchecked", null],
  off: ["cnBadgeOff", null], missing: ["cnBadgeMissing", "warn"],
};
const badgeHTML = (kind) => {
  const [key, icon] = BADGES[kind];
  return `<span class="cn-badge cn-badge--${kind}">${icon ? ico(icon, 13) : ""}${esc(t(key))}</span>`;
};

/* Дія → [ключ підпису, іконка, класи кнопки]. Імена дій — гачки `data-cn` для `app.js`. */
const ACTIONS = {
  enable: ["cnEnable", "plus", "ctl ctl--out"],
  configure: ["cnConfigure", "pencil", "ctl ctl--out"],
  check: ["cnCheck", "refresh", "ctl"],
  disable: ["cnDisable", null, "ctl"],
};

const detailHTML = (d) => (d ? `<span class="cn-why-detail">${esc(d)}</span>` : "");

function whyHTML(e) {
  const w = whyOf(e);
  if (!w) return "";
  return `<div class="cn-why">${ico("warn", 13)}<span>${esc(t(w.key))}${detailHTML(w.detail)}</span></div>`;
}

/** Картка модуля. `busy` — Map id → дія в польоті: її кнопки вимкнені, «Перевірити» каже «Перевіряю…». */
export function cardHTML(e, busy) {
  const v = cardView(e);
  const b = busy?.get?.(e.id) ?? null;
  const desc = builtinText(e.id)?.desc;
  const roles = rolesLine(e);
  const acts = v.actions.map((a) => {
    const [key, icon, cls] = ACTIONS[a];
    const label = a === "check" && b === "check" ? t("cnChecking") : t(key);
    return `<button class="${cls}" data-cn="${a}" data-id="${esc(e.id)}"${b ? " disabled" : ""}>`
      + `${icon ? ico(icon) : ""}${esc(label)}</button>`;
  }).join("");
  return `<div class="cn-card" data-id="${esc(e.id)}">
    <div class="cn-card-top"><span class="cn-ic">${ico(roleIcon(e.roles?.[0]))}</span>
      <div class="cn-card-name"><b>${esc(modName(e))}</b>${roles ? `<span class="cn-card-role">${esc(roles)}</span>` : ""}</div>
      ${v.implicit ? `<span class="cn-tag">${esc(t("cnImplicit"))}</span>` : ""}${badgeHTML(v.badge)}</div>
    ${desc ? `<p class="cn-card-desc">${esc(t(desc))}</p>` : ""}
    ${v.why ? whyHTML(e) : ""}
    <div class="cn-card-acts">${acts}</div></div>`;
}

/**
 * Рядок «Зараз» секції ролі (`''`, коли `capabilities` ролі не знають). Експортований, бо гілка `kind: 'error'`
 * (space.json не читається) через `connPageHTML` недосяжна: сторінка тоді віддає лише помилку без секцій — а
 * охоронному рядку все одно потрібен прямий тест, інакше він загнив би непоміченим.
 */
export function nowHTML(role, v) {
  const p = providerLine(role, v.space?.capabilities, v.list);
  if (!p) return "";
  const txt = p.kind === "legacy" ? t("cnNowLegacy")
    : p.kind === "error" ? t("cnNowError")
      : p.kind === "none" ? (p.noneKey ? t("cnNowNone", t(p.noneKey)) : t("cnNowNobody"))
        : t("cnNow", p.entry ? modName(p.entry) : p.id);
  return `<span class="cn-now">${esc(txt)}</span>`;
}

function sectionHTML(s, i, v) {
  const keys = roleKeys(s.role);
  return `<section class="cn-sec" aria-labelledby="cn-sec-${i}">
    <div class="cn-sec-head"><h2 class="cn-sec-h" id="cn-sec-${i}">${esc(roleTitle(s.role))}</h2>${nowHTML(s.role, v)}</div>
    ${keys ? `<p class="cn-sec-lead">${esc(t(keys.lead))}</p>` : ""}
    <div class="cn-grid">${s.modules.map((e) => cardHTML(e, v.busy)).join("")}</div></section>`;
}

const agentHTML = (sp) => `<div class="cn-agent">${ico("task")}<div><b>${esc(t("cnAgentTitle"))}</b> ${esc(t("cnAgentText"))}
    <code class="cn-code">GET /api/modules?space=${esc(encodeURIComponent(sp.id))}</code>
    <code class="cn-code">POST /api/module-enable {space: "${esc(sp.id)}", id, settings, secrets, replace}</code>
    <code class="cn-code">POST /api/module-settings · /api/module-check · /api/module-disable</code></div></div>`;

/** Сторінка «Підключення». Простору нема — порожньо (входів тоді нема, `app.js` сюди не пускає). */
export function connPageHTML(v) {
  const sp = v?.space;
  if (!sp) return "";
  const head = `<h1 class="th-h" id="cn-title">${esc(t("cnTitleIn", sp.name))}</h1>
    <p class="cn-lead">${esc(t("cnLead"))} ${esc(t("cnLeadWhere", sp.path || ""))}</p>`;
  const wrap = (inner) => `<div class="th-in cn-in">${head}${inner}</div>`;
  /* space.json не читається — двома шляхами: сервер сказав у `capabilities.error` або відмовив списку модулів
     (`409 space-json-unreadable`). В обох випадках решта `capabilities` нічого не варта, картки не малюємо. */
  const sjBad = !!sp.capabilities?.error || v.failed?.code === "space-json-unreadable";
  if (sjBad || v.failed) {
    const msg = sjBad ? t("cnErrSpaceJson", sp.path || "") : t("cnErrLoad");
    const det = !sjBad && v.failed?.message ? detailHTML(String(v.failed.message).slice(0, DETAIL_MAX)) : "";
    return wrap(`<div class="cn-err" role="alert">${ico("warn")}<span>${esc(msg)}${det}</span>`
      + `<button class="ctl ctl--out" data-cn="retry">${ico("refresh")}${esc(t("retry"))}</button></div>`);
  }
  if (!Array.isArray(v.list)) return wrap(`<p class="cn-loading" role="status">${esc(t("cnLoading"))}</p>`);
  const { sections, missing } = groupModules(v.list);
  const miss = missing.length
    ? `<section class="cn-sec" aria-labelledby="cn-sec-miss"><div class="cn-sec-head"><h2 class="cn-sec-h" id="cn-sec-miss">`
      + `${esc(t("cnMissingSec"))}</h2></div><div class="cn-grid">${missing.map((e) => cardHTML(e, v.busy)).join("")}</div></section>`
    : "";
  return wrap(`${sections.map((s, i) => sectionHTML(s, i, v)).join("")}${miss}${agentHTML(sp)}`);
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
 *
 * ⚠️ Примітку стирання (`-erase`) у `aria-describedby` кладемо лише коли секрет ПОЗНАЧЕНО до стирання: елемент із
 * `hidden`, на який указує `aria-describedby`, усе одно озвучується — «буде стерто після збереження» звучало б при
 * кожному непозначеному секреті. Хто перемикає позначку без перемальовки (`toggleCnErase`), мусить так само
 * додати/зняти цей id в атрибуті поля.
 */
function fieldHTML(e, f, i, d) {
  const id = `cn-f-${i}`;
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

function resultHTML(r) {
  if (!r) return "";
  if (r.kind === "ok") {
    return `<div class="cn-res cn-res--ok" role="status">${ico("check", 13)}<span>${esc(t(r.key))}${detailHTML(r.detail)}</span></div>`;
  }
  const head = r.kind === "failed" ? `<b>${esc(t("cnSavedButFailed"))}</b> ` : "";
  return `<div class="cn-res cn-res--err" role="alert">${ico("warn", 13)}<span>${head}${esc(t(r.key))}${detailHTML(r.detail)}</span></div>`;
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
    <div class="cn-dr-foot">${d.mode === "edit"
      ? `<button type="button" class="ctl ctl--out" data-cn-dr="check"${d.busy ? " disabled" : ""}>${ico("refresh")}${esc(checkLabel)}</button>` : ""}
      <span class="cn-grow"></span>
      <button type="submit" class="ctl ctl--pri" data-cn-dr="submit"${d.busy ? " disabled" : ""}>${esc(primary)}</button></div></form>`;
}
