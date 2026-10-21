/**
 * Розмітка майстра нового простору (Deai 0.6.0, етап 3b; спека
 * `docs/superpowers/specs/2026-10-21-first-run-wizard-design.md`). Чисті будівельники рядків — ні DOM, ні fetch.
 * Логіка — `wizard-model.js`; поля модулів, бейдж і результат запису — СПІЛЬНІ з бічною панеллю 3a
 * (`connections-view.js`), щоб майстер і «Підключення» не розійшлись.
 *
 *   wizardHTML(v)   v = {step: 1..4, created, busy: false|'save', s1, s2, s3, s4}
 *     s1 = {name, color, path, folderFirst}   (`folderFirst` — для контролера: фокус у поле теки; розмітка його не читає)
 *     s2 = {list|null, failed|null, capsError, pick: Set, path}
 *     s3 = {cards: [{entry, fields, values, erase, errors, result}], offs: [{role, holder, result}], failed|null, loading}
 *          offs — рядки «буде вимкнено»: `offRows` ∪ `errOffRows` моделі, `result` — відповідь вимкнення (`resultHTML`) або `null`
 *     s4 = {title, id, source: 'empty'|'folder', from, spaceName, tasks}
 *
 * Гачки (контракт для `wizard.js` і живих тестів): корінь `.wz[data-step]`; заголовок `#wz-h` (tabindex=-1); форма кроку
 * `form[data-wz-step]` (крок 1 — ще й `data-form="space" data-mode="new|edit"`, крок 4 — `data-form="task"`); головна
 * кнопка `[data-a="ok"]` (type=submit); «Скасувати» `[data-a="cancel"]`; інші кнопки `[data-wz="back|close|skip|copy|retry"]`;
 * радіо кроку 2 `input[data-wz-pick][data-role]` (value — id модуля, порожнє — «Без модуля»), id `wz-o-<секція>-<варіант|none>`;
 * картка кроку 3 `.wz-card[data-id]` з полями 3a (`data-cn-field`, id `wz-f-<картка>-<поле>`); рядок «Без модуля»
 * `.wz-off[data-id]` (обидва — `tabindex="-1"`: контролер ставить фокус на контейнер збійної картки/рядка без контролів);
 * «Спробувати ще» `[data-wz="retry"]` — на кроках 2 і 3, коли список модулів не прочитався (на кроці 3 «Зберегти й далі» тоді
 * вимкнена); крок 4 — `#tf-title`, `#tf-id`, `input[name="wz-src"]`, `#wz-from`; слот помилки `#wz-err` (кроки 1 і 4:
 * лише їхні форми правляться на місці; кроки 2–3 перемальовуються, їхні відмови живуть у картках і рядках).
 * Ідентифікатори кроку 1 (`#sp-name`, `#sp-path`, `#sp-found`, `#sp-registered`, `.cv-colors`, `input[name=color]`) — ті,
 * що чекає `wireSpaceDialog`; кроку 4 (`#tf-title`, `#tf-id`) — ті, що чекає `wireTaskForm`.
 *
 * ⛔ Усе з даних — лише через `esc()`; колір — лише через `spaceColorToken`. Секрет у розмітку не потрапляє ніколи (поле
 * пароля малює `fieldHTML` 3a — завжди порожнім).
 */
import { esc } from "./esc.js";
import { ico } from "./icons.js";
import { t } from "./i18n.js";
import { DETAIL_MAX, builtinText, cardView, roleHolders, roleIcon, roleKeys, whyOf } from "./connections-model.js";
import { badgeHTML, fieldHTML, modName, resultHTML, roleTitle, rolesLine, whyHTML } from "./connections-view.js";
import { SPACE_COLORS, spaceColorToken } from "./spaces-model.js";
import { pickedFor, wizardSections } from "./wizard-model.js";

const STEP_KEYS = ["wzStep1", "wzStep2", "wzStep3", "wzStep4"];

/** Смужка кроків: для ока — смужки, для читача екрана — назви (`.wz-step-name` візуально прихована). */
function stepsHTML(step) {
  const items = STEP_KEYS.map((k, i) => {
    const n = i + 1;
    const st = n < step ? "done" : n === step ? "cur" : "todo";
    return `<li class="wz-step wz-step--${st}"${n === step ? ' aria-current="step"' : ""}>`
      + `<span class="wz-step-bar" aria-hidden="true"></span><span class="wz-step-name">${esc(t(k))}</span></li>`;
  }).join("");
  return `<ol class="wz-steps" aria-label="${esc(t("wzSteps"))}">${items}</ol>`
    + `<p class="wz-of">${esc(t("wzStepOf", step, STEP_KEYS.length, t(STEP_KEYS[step - 1])))}</p>`;
}

const head = (titleKey, lead) => `<h1 class="th-h wz-h" id="wz-h" tabindex="-1">${esc(t(titleKey))}</h1>`
  + `<p class="wz-lead">${esc(lead)}</p>`;
const errSlot = `<p class="wz-err" id="wz-err" role="alert" hidden></p>`;
const foot = (left, right) => `<div class="wz-foot">${left}<span class="cn-grow"></span>${right}</div>`;
const btn = (attrs, label, { cls = "ctl ctl--out", icon = "", dis = false } = {}) =>
  `<button type="button" class="${cls}" ${attrs}${dis ? " disabled" : ""}>${icon ? ico(icon) : ""}${esc(label)}</button>`;
const ok = (label, dis) => `<button type="submit" class="ctl ctl--pri" data-a="ok"${dis ? " disabled" : ""}>${esc(label)}</button>`;
const backBtn = (dis) => btn('data-wz="back"', t("wzBack"), { icon: "chevleft", dis });
const closeBtn = (dis) => btn('data-wz="close"', t("wzClose"), { cls: "ctl ctl--ghost", dis });
const detail = (s) => (s ? `<span class="cn-why-detail">${esc(String(s).slice(0, DETAIL_MAX))}</span>` : "");

/* ── крок 1 · Простір ─────────────────────────────────────────────────────────────────────────────── */

function colorsHTML(colorIn, dis) {
  const color = spaceColorToken(colorIn);
  const items = SPACE_COLORS.map((c, i) => `<button type="button" class="cv-color" role="radio" data-val="${c}"`
    + ` aria-checked="${c === color}" tabindex="${c === color ? 0 : -1}" aria-label="${esc(t("spaceColorName", i + 1))}"`
    + ` style="background:var(--${c})"${dis ? " disabled" : ""}>${ico("check", 14)}</button>`).join("");
  return `<div class="cv-colors wz-colors" role="radiogroup" aria-labelledby="sp-color-l">${items}</div>`
    + `<input type="hidden" name="color" value="${color}">`;
}

function step1HTML(v) {
  const s = v.s1;
  const edit = !!v.created;
  const busy = !!v.busy;
  const dis = busy ? " disabled" : "";
  const folder = edit
    ? `<input class="cn-inp" id="sp-path" name="path" type="text" value="${esc(s.path)}" readonly aria-describedby="wz-s1-hint">
      <p class="cn-hint" id="wz-s1-hint">${esc(t("wzS1FolderLocked"))}</p>`
    : `<input class="cn-inp" id="sp-path" name="path" type="text" value="${esc(s.path)}" autocomplete="off" spellcheck="false"
        aria-describedby="sp-found sp-registered wz-s1-hint wz-err"${dis}>
      <p class="cn-hint" id="sp-found" role="status" hidden></p>
      <p class="cn-hint" id="sp-registered" role="status" hidden></p>
      <p class="cn-hint" id="wz-s1-hint">${esc(t("wzS1FolderHint"))}</p>`;
  const label = busy ? t(edit ? "wzSaving" : "wzCreating") : t("wzNext");
  const left = edit ? closeBtn(busy) : btn('data-a="cancel"', t("wzCancel"), { cls: "ctl ctl--ghost", dis: busy });
  return `${head(edit ? "wzS1TitleEdit" : "wzS1Title", t("wzS1Lead"))}
    <form class="wz-form" data-wz-step="1" data-form="space" data-mode="${edit ? "edit" : "new"}" novalidate${busy ? ' aria-busy="true"' : ""}>
      <div class="cn-field"><label class="cn-lbl" for="sp-name">${esc(t("spaceName"))}</label>
        <input class="cn-inp" id="sp-name" name="name" type="text" value="${esc(s.name)}" maxlength="60" autocomplete="off"
          spellcheck="false" placeholder="${esc(t("spaceNamePh"))}" aria-describedby="wz-err"${dis}></div>
      <div class="cn-field"><span class="cn-lbl" id="sp-color-l">${esc(t("spaceColor"))}</span>${colorsHTML(s.color, busy)}</div>
      <div class="cn-field"><label class="cn-lbl" for="sp-path">${esc(t("spaceFolder"))}</label>${folder}</div>
      ${errSlot}
      ${foot(left, ok(label, busy))}
    </form>`;
}

/* ── крок 2 · Модулі ─────────────────────────────────────────────────────────────────────────────── */

function optionHTML(e, i, j, role, s, dis) {
  const id = `wz-o-${i}-${j}`;
  const on = pickedFor(s.pick, s.list, role) === e.id;
  const desc = builtinText(e.id)?.desc;
  /* «Замість кого»: поточні тримачі ролей цього модуля (зі списку сервера), коли сам він ще не ввімкнений. */
  const instead = e.enabled === true ? [] : roleHolders(e, s.list);
  const why = e.status === "error" ? whyOf(e) : null;
  return `<label class="wz-opt" for="${id}"><input type="radio" id="${id}" name="wz-r-${i}" value="${esc(e.id)}"`
    + ` data-wz-pick data-role="${esc(role)}"${on ? " checked" : ""}${dis}>`
    + `<span class="wz-opt-body"><span class="wz-opt-top"><b>${esc(modName(e))}</b>`
    + `${e.implicit === true ? `<span class="cn-tag">${esc(t("cnImplicit"))}</span>` : ""}</span>`
    + `${desc ? `<span class="wz-opt-desc">${esc(t(desc))}</span>` : ""}`
    + `${instead.length ? `<span class="wz-opt-instead">${esc(t("wzInstead", instead.map(modName).join(", ")))}</span>` : ""}`
    + `${why ? `<span class="wz-opt-why">${ico("warn", 13)}<span>${esc(t(why.key))}${detail(why.detail)}</span></span>` : ""}`
    + `</span></label>`;
}

function noneHTML(i, role, s, dis) {
  const id = `wz-o-${i}-none`;
  const on = !pickedFor(s.pick, s.list, role);
  const k = roleKeys(role)?.none;
  return `<label class="wz-opt wz-opt--none" for="${id}"><input type="radio" id="${id}" name="wz-r-${i}" value=""`
    + ` data-wz-pick data-role="${esc(role)}"${on ? " checked" : ""}${dis}>`
    + `<span class="wz-opt-body"><span class="wz-opt-top"><b>${esc(t("wzNone"))}</b></span>`
    + `${k ? `<span class="wz-opt-desc">${esc(t(k))}</span>` : ""}</span></label>`;
}

function step2HTML(v) {
  const s = v.s2;
  const busy = !!v.busy;
  const dis = busy ? " disabled" : "";
  let body;
  let loading = false;
  if (s.capsError) {
    body = `<div class="cn-err" role="alert">${ico("warn")}<span>${esc(t("cnErrSpaceJson", s.path || ""))}</span></div>`;
  } else if (s.failed) {
    body = `<div class="cn-err" role="alert">${ico("warn")}<span>${esc(t("cnErrLoad"))}${detail(s.failed.message)}</span>`
      + `${btn('data-wz="retry"', t("retry"), { icon: "refresh" })}</div>`;
  } else if (!Array.isArray(s.list)) {
    loading = true;
    body = `<p class="cn-loading" role="status">${esc(t("cnLoading"))}</p>`;
  } else {
    body = wizardSections(s.list).map((sec, i) => {
      const k = roleKeys(sec.role)?.lead;
      /* Лід секції читач екрана чує разом із групою: `aria-describedby` лише коли лід є (висяче посилання — вада). */
      return `<fieldset class="wz-sec"${k ? ` aria-describedby="wz-sl-${i}"` : ""}><legend class="cn-sec-h">${esc(roleTitle(sec.role))}</legend>`
        + `${k ? `<p class="cn-sec-lead" id="wz-sl-${i}">${esc(t(k))}</p>` : ""}<div class="wz-opts">`
        + sec.modules.map((e, j) => optionHTML(e, i, j, sec.role, s, dis)).join("")
        + noneHTML(i, sec.role, s, dis) + `</div></fieldset>`;
    }).join("");
  }
  return `${head("wzS2Title", t("wzS2Lead"))}
    <form class="wz-form" data-wz-step="2" novalidate>${body}
      ${foot(`${backBtn(busy)}${closeBtn(busy)}`, ok(t("wzNext"), busy || loading))}</form>`;
}

/* ── крок 3 · Налаштування ───────────────────────────────────────────────────────────────────────── */

function cardHTML(c, i, busy) {
  const e = c.entry;
  const badge = e.enabled === true ? badgeHTML(cardView(e).badge)
    : `<span class="cn-badge">${esc(t("wzBadgeWill"))}</span>`;
  const desc = builtinText(e.id)?.desc;
  const roles = rolesLine(e);
  const d = { errors: c.errors ?? {}, form: { values: c.values ?? {}, erase: c.erase ?? [] }, busy };
  const fields = (c.fields ?? []).map((f, j) => fieldHTML(e, f, j, d, `wz-f-${i}`)).join("");
  /* `tabindex="-1"` — контролер ставить фокус на контейнер, коли в збійної картки нема контролів. */
  return `<section class="cn-card wz-card" data-id="${esc(e.id)}" tabindex="-1" aria-labelledby="wz-c-${i}">
    <div class="cn-card-top"><span class="cn-ic">${ico(roleIcon(e.roles?.[0]))}</span>
      <div class="cn-card-name"><b id="wz-c-${i}">${esc(modName(e))}</b>${roles ? `<span class="cn-card-role">${esc(roles)}</span>` : ""}</div>
      ${badge}</div>
    ${desc ? `<p class="cn-card-desc">${esc(t(desc))}</p>` : ""}
    ${cardView(e).why ? whyHTML(e) : ""}
    ${fields}<div class="wz-res" data-wz-res="${esc(e.id)}">${resultHTML(c.result)}</div></section>`;
}

function offHTML(o) {
  const k = roleKeys(o.role)?.none;
  const text = k ? t("wzOffRow", roleTitle(o.role), modName(o.holder), t(k))
    : t("wzOffRowPlain", roleTitle(o.role), modName(o.holder));
  return `<li class="wz-off" data-id="${esc(o.holder.id)}" tabindex="-1">${ico("x", 13)}<span>${esc(text)}</span>${resultHTML(o.result)}</li>`;
}

function step3HTML(v) {
  const s = v.s3;
  const busy = !!v.busy;
  let body;
  if (s.loading) body = `<p class="cn-loading" role="status">${esc(t("cnLoading"))}</p>`;
  else if (s.failed) {
    /* Як на кроці 2: не глухий кут — «Спробувати ще», а «Зберегти й далі» вимкнена (список не прочитався, писати нема що). */
    body = `<div class="cn-err" role="alert">${ico("warn")}<span>${esc(t("cnErrLoad"))}${detail(s.failed.message)}</span>`
      + `${btn('data-wz="retry"', t("retry"), { icon: "refresh" })}</div>`;
  } else {
    const offs = s.offs.length ? `<ul class="wz-offs">${s.offs.map(offHTML).join("")}</ul>` : "";
    const cards = s.cards.length
      ? `<fieldset class="wz-cards"${busy ? " disabled" : ""}>${s.cards.map((c, i) => cardHTML(c, i, busy)).join("")}</fieldset>`
      : (offs ? "" : `<p class="cn-dr-none">${esc(t("wzS3Nothing"))}</p>`);
    body = offs + cards;
  }
  return `${head("wzS3Title", t("wzS3Lead"))}
    <form class="wz-form" data-wz-step="3" novalidate>${body}
      ${foot(`${backBtn(busy)}${closeBtn(busy)}`, ok(busy ? t("wzSaving") : t("wzSaveNext"), busy || s.loading || !!s.failed))}</form>`;
}

/* ── крок 4 · Перша задача ───────────────────────────────────────────────────────────────────────── */

function step4HTML(v) {
  const s = v.s4;
  const busy = !!v.busy;
  const dis = busy ? " disabled" : "";
  const folder = s.source === "folder";
  const lead = s.tasks > 0 ? t("wzS4LeadHas", s.tasks) : t("wzS4Lead");
  const radio = (val, key) => `<label class="cn-check"><input type="radio" name="wz-src" value="${val}"`
    + `${(val === "folder") === folder ? " checked" : ""}${dis}> ${esc(t(key))}</label>`;
  const form = `<form class="wz-form wz-task" data-wz-step="4" data-form="task" novalidate${busy ? ' aria-busy="true"' : ""}>
      <div class="cn-field"><label class="cn-lbl" for="tf-title">${esc(t("newTaskTitle"))}</label>
        <input class="cn-inp" id="tf-title" name="title" type="text" value="${esc(s.title)}" autocomplete="off"
          placeholder="${esc(t("newTaskTitlePh"))}" aria-describedby="wz-err"${dis}></div>
      <div class="cn-field"><label class="cn-lbl" for="tf-id">${esc(t("newTaskId"))}</label>
        <input class="cn-inp" id="tf-id" name="id" type="text" value="${esc(s.id)}" autocomplete="off" spellcheck="false"
          aria-describedby="wz-err"${dis}></div>
      <fieldset class="wz-src"><legend class="cn-lbl">${esc(t("wzSource"))}</legend>
        ${radio("empty", "wzSourceEmpty")}${radio("folder", "wzSourceFolder")}</fieldset>
      <div class="cn-field" id="wz-from-f"${folder ? "" : " hidden"}><label class="cn-lbl" for="wz-from">${esc(t("wzFromLabel"))}</label>
        <input class="cn-inp" id="wz-from" name="from" type="text" value="${esc(s.from)}" autocomplete="off" spellcheck="false"
          placeholder="~/" aria-describedby="wz-from-hint wz-err"${dis}>
        <p class="cn-hint" id="wz-from-hint">${esc(t("wzFromHint"))}</p></div>
      ${errSlot}
      <div class="wz-acts">${ok(busy ? t("wzCreating") : t("wzCreateOpen"), busy)}</div></form>`;
  const agent = `<aside class="cn-agent wz-agent">${ico("task")}<div><b>${esc(t("wzAgentTitle"))}</b> ${esc(t("wzAgentText"))}
      <code class="cn-code" id="wz-phrase">${esc(t("wzAgentPhrase", s.spaceName))}</code>
      <div class="wz-acts">${btn('data-wz="copy"', t("wzCopy"), { icon: "copy" })}</div></div></aside>`;
  return `${head("wzS4Title", lead)}<div class="wz-two">${form}${agent}</div>
    ${foot(backBtn(busy), btn('data-wz="skip"', t(s.tasks > 0 ? "wzToTasks" : "wzSkip"), { cls: "ctl ctl--ghost", dis: busy }))}`;
}

/** Уся сторінка майстра для `#tasks-home`. */
export function wizardHTML(v) {
  const step = Number(v.step);          // у розмітку — лише число (`data-step` не бере рядок із даних як є)
  const body = [step1HTML, step2HTML, step3HTML, step4HTML][step - 1](v);
  return `<div class="th-in wz" data-step="${step}">${stepsHTML(step)}${body}</div>`;
}
