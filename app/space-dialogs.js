/**
 * Діалоги просторів: розмітка діалогу простору, форми «Нова задача» й привітання,
 * плюс проводка полів цих форм. Розмітка — ЧИСТІ рядки (як `shell-bar.js`): ні
 * мережі, ні стану модуля; проводка — функції `wire*`, що беруть готовий вузол
 * `<form>` і залежності ЗВЕРХУ (`peek`, `taken`), тож тут нема жодного `fetch` і
 * жодного імпорту `app.js`. Оболонку діалогу (одиночність, Esc, фокус-пастка, відправка,
 * показ помилки) дає `askForm` з `ask.js`; тут лише те, що в ньому показується.
 *
 * ⛔ Усе, що приходить із даних (назва простору, тека, текст помилки), іде в розмітку
 * ЛИШЕ через `esc()`; колір — лише через `spaceColorToken` (токен у `style`, а не рядок
 * із реєстру, який правлять руками).
 *
 * Стабільні гачки для живих тестів (Task 8) — це контракт, а не косметика:
 *   діалог простору  `form[data-form="space"][data-mode="new|edit"]`; поля `#sp-name`
 *                    (`name="name"`), `#sp-path` (`name="path"`, лише в `new`),
 *                    прихований `name="color"`; кружки `.cv-color[role=radio][data-val]`;
 *                    підказка «тека вже простір» `#sp-found`; підказка «цю теку вже додано»
 *                    (тека є в реєстрі) `#sp-registered`;
 *   форма задачі     `form[data-form="task"]`; поля `#tf-title` (`name="title"`),
 *                    `#tf-id` (`name="id"`);
 *   спільне          слот помилки `[data-form-error]`, кнопки `button[data-a="ok"]`
 *                    (type=submit) і `button[data-a="cancel"]`;
 *   привітання       кнопка `[data-th="spacenew"]` у `.th-welcome`.
 */
import { esc } from "./esc.js";
import { ico } from "./icons.js";
import { t } from "./i18n.js";
import { LOGO_SVG } from "./logo.js";
import {
  SPACE_COLORS, colorStep, defaultSpacePath, peekFound, peekRegistered, spaceColorToken, taskIdFrom,
} from "./spaces-model.js";

/* Слот помилки один на форму (оверлей один на канвас), тож id сталий. Поля посилаються на
   нього через `aria-describedby`; який саме поле помилкове, каже `aria-invalid`, його ставить
   `ctl.focus(імʼя)` (`ask.js`). */
const ERR_ID = "cv-form-err";

/** Слот помилки: схований, поки порожній. `errorKey` — початкова помилка (рідко: живі йдуть через `ctl.error`). */
const errorSlot = (errorKey) =>
  `<p class="cv-form-err" id="${ERR_ID}" role="alert" data-form-error${errorKey ? "" : " hidden"}>${errorKey ? esc(t(errorKey)) : ""}</p>`;

/** Рядок кнопок діалогу. Відправка — `type=submit`: Enter у полі й клік ідуть одним шляхом. */
const buttons = (okKey) => `<div class="cv-ask-row">
  <button type="button" data-a="cancel">${esc(t("askCancel"))}</button>
  <button type="submit" data-a="ok">${esc(t(okKey))}</button></div>`;

/**
 * Шість кружків кольору. `role="radio"` у `role="radiogroup"` — не нативні `<input
 * type=radio>`: кружок мусить бути кольоровою плиткою без нативного вигляду. Тож
 * клавіатуру (roving tabindex: лише вибраний у Tab-порядку; стрілки ходять по колу)
 * дає `wireSpaceDialog`. Вибраний позначений не лише рамкою, а й галочкою — колір
 * сам стан не оголошує.
 */
function colorGroup(colorIn, locked) {
  const color = spaceColorToken(colorIn);   // токен, не рядок із реєстру: іде в `style` і `value`
  const items = SPACE_COLORS.map((c, i) => `<button type="button" class="cv-color" role="radio"
    data-val="${c}" aria-checked="${c === color}" tabindex="${c === color ? 0 : -1}"
    aria-label="${esc(t("spaceColorName", i + 1))}" style="background:var(--${c})">${ico("check", 14)}</button>`).join("");
  return `<div class="cv-colors" role="radiogroup" aria-labelledby="sp-color-l"${locked ? ' aria-disabled="true"' : ""}>${items}</div>
    <input type="hidden" name="color" value="${color}">`;
}

/**
 * Діалог простору. `mode`: `new` — назва, колір, ТЕКА; `edit` — лише назва й колір
 * (теку простору міняти не можна: на ній стоїть реєстр і його задачі). `found` —
 * `{name}` простору, що вже лежить у вказаній теці (див. `peekFound`): тоді назва й
 * колір — ЙОГО, а не набрані (сервер `space.json` не перезаписує), тож поле назви
 * тільки для читання, кружки заблоковані, а підказка пояснює чому.
 */
export function spaceDialogHTML({ mode = "new", name = "", color = SPACE_COLORS[0], path = "", found = null, errorKey = "" } = {}) {
  const isNew = mode !== "edit";
  const folder = isNew ? `<div class="cv-field">
    <label for="sp-path">${esc(t("spaceFolder"))}</label>
    <input id="sp-path" name="path" type="text" value="${esc(path)}" autocomplete="off" spellcheck="false"
      aria-describedby="sp-found sp-registered ${ERR_ID}">
    <p class="cv-hint" id="sp-found" role="status"${found ? "" : " hidden"}>${found ? esc(t("spaceFound", found.name)) : ""}</p>
    <p class="cv-hint" id="sp-registered" role="status" hidden></p>
    <p class="cv-hint">${esc(t("spaceFolderHint"))}</p>
    <p class="cv-hint">${esc(t("integrationsOff"))}</p></div>` : "";
  return `<form class="cv-form" data-form="space" data-mode="${isNew ? "new" : "edit"}" novalidate
    role="dialog" aria-modal="true" aria-labelledby="sp-h">
    <h2 class="cv-form-h" id="sp-h">${esc(t(isNew ? "spaceNewTitle" : "spaceEditTitle"))}</h2>
    ${isNew ? `<p class="cv-form-lead">${esc(t("spaceNewLead"))}</p>` : ""}
    <div class="cv-field">
      <label for="sp-name">${esc(t("spaceName"))}</label>
      <input id="sp-name" name="name" type="text" value="${esc(name)}" maxlength="60" autocomplete="off"
        spellcheck="false" placeholder="${esc(t("spaceNamePh"))}"${found ? " readonly" : ""} aria-describedby="${ERR_ID}" data-autofocus>
    </div>
    <div class="cv-field">
      <span class="cv-lbl" id="sp-color-l">${esc(t("spaceColor"))}</span>
      ${colorGroup(color, !!found)}
    </div>
    ${folder}
    ${errorSlot(errorKey)}
    ${buttons(isNew ? "spaceCreate" : "spaceSave")}
  </form>`;
}

/** Форма «Нова задача»: назва й ідентифікатор (id підставляє `wireTaskForm`, поки його не правили руками). */
export function taskFormHTML({ title = "", id = "", errorKey = "" } = {}) {
  return `<form class="cv-form" data-form="task" novalidate role="dialog" aria-modal="true" aria-labelledby="tf-h">
    <h2 class="cv-form-h" id="tf-h">${esc(t("newTask"))}</h2>
    <div class="cv-field">
      <label for="tf-title">${esc(t("newTaskTitle"))}</label>
      <input id="tf-title" name="title" type="text" value="${esc(title)}" autocomplete="off"
        placeholder="${esc(t("newTaskTitlePh"))}" aria-describedby="${ERR_ID}" data-autofocus>
    </div>
    <div class="cv-field">
      <label for="tf-id">${esc(t("newTaskId"))}</label>
      <input id="tf-id" name="id" type="text" value="${esc(id)}" autocomplete="off" spellcheck="false"
        aria-describedby="${ERR_ID}">
    </div>
    ${errorSlot(errorKey)}
    ${buttons("taskCreate")}
  </form>`;
}

/**
 * Привітання — машина, на якій просторів ще нема. Малюється у вузлі екрана «Задачі»
 * (`#tasks-home`) замість списку: дорога звідси одна — створити перший простір. Фраза
 * про агента — не прикраса: агент уміє заводити простори тим самим API.
 */
export function welcomeHTML() {
  return `<div class="th-in th-welcome">
    <div class="th-welcome-logo">${LOGO_SVG}</div>
    <h1 class="th-h">${esc(t("welcomeTitle"))}</h1>
    <p class="th-welcome-lead">${esc(t("welcomeLead"))}</p>
    <div class="th-welcome-act"><button class="ctl ctl--pri" data-th="spacenew">${ico("plus")}${esc(t("welcomeCreate"))}</button></div>
    <p class="th-welcome-agent">${esc(t("welcomeAgent"))}</p></div>`;
}

/* ── проводка полів ──────────────────────────────────────────────────────── */

/**
 * Проводка діалогу простору. `peek(path)` — `Promise<відповідь /api/space-peek>`; `taken` —
 * шляхи просторів, що вже в реєстрі (масив або функція, що його віддає: реєстр може
 * оновитись, поки діалог відкритий); решта — вузли самої форми. Що робить:
 *   · кружки: клік вибирає, стрілки ходять по колу (`colorStep`), вибраний — єдиний у Tab;
 *   · `new`: тека йде за назвою (`defaultSpacePath`, ВІЛЬНА — не зайнята іншим простором),
 *     доки її не правили руками;
 *   · `new`: через `debounceMs` після зміни теки питає `peek`; тека, що вже простір, —
 *     назва й колір підставляються її власні й блокуються (див. `spaceDialogHTML`);
 *     тека, що вже ЗАРЕЄСТРОВАНА, — не «знайдений простір»: форма лишається редагованою, а
 *     окрема підказка каже, що її вже додано (сервер однаково відмовить `path-registered`).
 *     Чи зареєстрована, каже передусім сам сервер (`registered` у відповіді peek: він бачить і
 *     варіант регістру), а лише без нього — порівняння за переліком `taken` (`peekRegistered`).
 * Відповіді peek, що прийшли не в порядку чи вже після закриття діалогу, відкидаються.
 */
export function wireSpaceDialog(form, { mode = "new", peek, debounceMs = 300, taken = [] } = {}) {
  const takenNow = () => (typeof taken === "function" ? taken() : taken) ?? [];
  const name = form.querySelector("#sp-name");
  const path = form.querySelector("#sp-path");
  const hint = form.querySelector("#sp-found");
  const regHint = form.querySelector("#sp-registered");
  const group = form.querySelector(".cv-colors");
  const colorInput = form.querySelector('input[name="color"]');
  const swatches = [...form.querySelectorAll(".cv-color")];

  /* Вибраний колір — ОДНЕ значення (приховане поле), решта — його відображення:
     `aria-checked` і tabindex виводяться з нього, а не живуть окремо. */
  const setColor = (c) => {
    const col = spaceColorToken(c);
    colorInput.value = col;
    for (const s of swatches) {
      s.setAttribute("aria-checked", String(s.dataset.val === col));
      s.tabIndex = s.dataset.val === col ? 0 : -1;
    }
  };
  const locked = () => group.getAttribute("aria-disabled") === "true";
  group.addEventListener("click", (ev) => {
    const b = ev.target.closest(".cv-color");
    if (b && !locked()) setColor(b.dataset.val);
  });
  group.addEventListener("keydown", (ev) => {
    const to = colorStep(colorInput.value, ev.key);
    if (!to || locked()) return;
    ev.preventDefault();
    setColor(to);
    swatches.find((s) => s.dataset.val === to)?.focus();
  });

  if (mode === "edit" || !path) return;

  let pathTouched = false;
  let stash = null;           // що людина набрала сама, поки поля показують чужий простір
  let seq = 0;
  let timer = null;

  const applyFound = (found) => {
    if (found) {
      if (!stash) stash = { name: name.value, color: colorInput.value };
      name.value = found.name;
      name.readOnly = true;
      setColor(found.color);
      group.setAttribute("aria-disabled", "true");
      hint.textContent = t("spaceFound", found.name);
      hint.hidden = false;
    } else if (stash) {
      name.value = stash.name;
      name.readOnly = false;
      setColor(stash.color);
      group.removeAttribute("aria-disabled");
      stash = null;
      hint.textContent = "";
      hint.hidden = true;
    }
  };
  const showRegistered = (on) => {
    if (!regHint) return;
    regHint.textContent = on ? t("spaceRegistered") : "";
    regHint.hidden = !on;
  };
  const askPeek = () => {
    clearTimeout(timer);
    const mine = ++seq;
    timer = setTimeout(async () => {
      if (!form.isConnected) return;
      let res;
      try { res = await peek(path.value); } catch (e) { return; }
      if (mine !== seq || !form.isConnected) return;
      const list = takenNow();
      applyFound(peekFound(res, list));
      showRegistered(peekRegistered(res, list));
    }, debounceMs);
  };
  name.addEventListener("input", () => {
    if (pathTouched || name.readOnly) return;
    path.value = defaultSpacePath(name.value, "~", takenNow());
    askPeek();
  });
  path.addEventListener("input", () => { pathTouched = true; askPeek(); });
  askPeek();
}

/**
 * Проводка форми «Нова задача». `taken` — `Promise<string[]>` або масив: id усіх задач
 * машини (`/api/tasks?all=1`). Доки `id` не правили руками, він іде за назвою
 * (`taskIdFrom` дає вільний, без регістру); очистили поле — автопідстановка вертається.
 * `taken` може приїхати ПІСЛЯ відкриття діалогу — тоді `id` перераховується.
 */
export function wireTaskForm(form, { taken = [] } = {}) {
  const title = form.querySelector("#tf-title");
  const id = form.querySelector("#tf-id");
  let ids = Array.isArray(taken) ? taken : [];
  let idTouched = id.value !== "";
  const sync = () => {
    if (!idTouched) id.value = title.value.trim() ? taskIdFrom(title.value, ids) : "";
  };
  title.addEventListener("input", sync);
  id.addEventListener("input", () => { idTouched = id.value !== ""; sync(); });
  if (!Array.isArray(taken)) {
    Promise.resolve(taken).then((list) => {
      if (Array.isArray(list)) { ids = list; if (form.isConnected) sync(); }
    }).catch(() => {});
  }
}
