/**
 * Майстер нового простору (Deai 0.6.0, етап 3b; спека `docs/superpowers/specs/2026-10-21-first-run-wizard-design.md`) —
 * стан, запити й події третьої сторінки оверлею `#tasks-home` (`homePage === 'wiz'`). Розмітку дає `wizard-view.js`,
 * рішення — `wizard-model.js`; тут лише проводка. Усе, що знає оболонка (запити, перехід між просторами, вихід з
 * оверлею, питання), приходить залежностями `createWizard(deps)` — модуль не імпортує `app.js`:
 *
 *   node()               вузол `#tasks-home`;
 *   api(path)            GET → JSON (кидає `Error` з `code`);   post(path, body) — POST зі стелею часу (`postForm`);
 *   askYesNo(q, opts)    питання;   toast(msg)   тост;   spaces()   остання відповідь `/api/spaces`;
 *   peek(path)           `/api/space-peek`;   takenPaths()   шляхи просторів;   takenTaskIds()   Promise<id[]> усіх задач;
 *   afterSpaceCreated()  простір створено й зроблено поточним (оболонка: `afterSpaceChange`);
 *   afterSpaceEdited(id, saved)   назва/колір змінились (`applySpaceMeta`);
 *   afterModulesChange() легкий шлях 3a після запису модулів;
 *   openTask(made)       задачу створено — відкрити її (вихід з оверлею);
 *   exit({back})         `back: false` — на «Задачі» (там і привітання, коли просторів нема); `back: true` («Скасувати» до
 *                        створення) — туди, звідки майстер відкрили (полотно задачі чи сторінка оверлею);
 *   copy(text)           у буфер обміну.
 *
 * Події сторінки (`click`, `submit`, `input`) делегує `wireHome` оболонки: `input` — і для `input`, і для `change`
 * (радіо модулів і джерела макета працюють на `change`).
 *
 * Простір майстра — `wz.spaceId` (після кроку 1): КОЖЕН запит кроків 2–4 несе його явно, бо агент міг перемкнути
 * активний простір паралельно. Відповідь `unknown-space` — майстер закривається (`spaceGone`).
 *
 * Перемальовка (`paint`) — повна: на зміні кроку, після перемикання мови, після кожного запису кроку 3. Набране в
 * полях вона не губить: `capture` забирає значення в стан (секрети — у ЛОКАЛЬНУ мапу), `restore` вертає. Зайнятість і
 * помилки кроків 1 і 4 НЕ перемальовують сторінку (`setBusy`, `showError` правлять вузли на місці): проводка
 * `wireSpaceDialog`/`wireTaskForm` тримає стан (тека правлена руками, id правлений руками), і повторна проводка його б
 * скинула (для перемальовки — опції `pathTouched`/`idTouched`). Якщо ж сторінку перемалювали, поки летів запит (мова),
 * форма, яку зробили зайнятою, відчеплена: `setBusy(…, false)` і `showError` тоді працюють із живою формою (перемальовка
 * без зайнятості), а не лишають її вимкненою.
 *
 * ⛔ Секрети: значення живуть лише у `.value` полів пароля (DOM) і в локальній змінній на час одного виклику. У стан
 * майстра, у розмітку чи в журнал не потрапляють. Після відповіді сервера на запис картки її поля паролів порожні.
 */
import { t } from "./i18n.js";
import {
  formFields, formPatch, initialForm, isDirty, missingRequired, refusalView, verdictText, writePayload,
} from "./connections-model.js";
import { modName } from "./connections-view.js";
import { wireSpaceDialog, wireTaskForm } from "./space-dialogs.js";
import {
  defaultSpacePath, freeColor, needsWelcome, spaceColorToken, spaceErrField, spaceErrKey, taskErrField, taskErrKey,
  taskFormError,
} from "./spaces-model.js";
import {
  allOk, errOffRows, holdersByRole, initialPick, offRows, pickModule, pickNone, pickedInOrder, prevStep, prunePick,
  titleFromFolder, writePlan,
} from "./wizard-model.js";
import { wizardHTML } from "./wizard-view.js";

/** Поточні значення полів модуля в межах `root` (картка): `{values, secrets, erase}` — як `readCnForm` панелі 3a. */
function readFields(root) {
  const values = [];
  const secrets = [];
  for (const n of root.querySelectorAll("[data-cn-field]")) {
    const k = n.dataset.cnField;
    if (n.dataset.type === "secret") secrets.push([k, n.value]);
    else if (n.dataset.type === "bool") values.push([k, n.checked]);
    else values.push([k, n.value]);
  }
  const erase = [...root.querySelectorAll('[data-cn-dr="erase"][aria-pressed="true"]')].map((b) => b.dataset.key);
  return { values: Object.fromEntries(values), secrets: Object.fromEntries(secrets), erase };
}

/** «Стерти» секрет у картці — без перемальовки (як `toggleCnErase` панелі 3a, але в межах картки). */
function toggleErase(btn) {
  const root = btn.closest(".wz-card");
  if (!root) return;
  const on = btn.getAttribute("aria-pressed") !== "true";
  btn.setAttribute("aria-pressed", String(on));
  const key = btn.dataset.key;
  const note = root.querySelector(`[data-cn-erase-note="${CSS.escape(key)}"]`);
  if (note) note.hidden = !on;
  const field = root.querySelector(`[data-cn-field="${CSS.escape(key)}"]`);
  if (field && note?.id) {
    const ids = (field.getAttribute("aria-describedby") || "").split(/\s+/).filter((x) => x && x !== note.id);
    if (on) ids.splice(ids.findIndex((x) => x.endsWith("-state")) + 1, 0, note.id);
    if (ids.length) field.setAttribute("aria-describedby", ids.join(" "));
    else field.removeAttribute("aria-describedby");
  }
}

export function createWizard(deps) {
  let wz = null;
  let busyFocus = null;       // що тримало фокус, коли форму зробили «зайнятою» (вимкнений контрол його втрачає)
  let busyForm = null;        // форма, яку `setBusy` зробила зайнятою: якщо її відчепили (перемальовка) — знімаємо зайнятість перемальовкою

  const spaceRec = () => (Array.isArray(deps.spaces()?.spaces) ? deps.spaces().spaces : []).find((x) => x.id === wz?.spaceId) ?? null;
  const painted = (el) => Number(el?.querySelector(".wz")?.dataset.step) || 0;
  const askDiscard = () => deps.askYesNo(t("wzDiscardAsk"), { yes: t("cnDiscard"), danger: true });
  const focusLost = () => !document.activeElement || document.activeElement === document.body;

  /** Відкрити на кроці 1. `folderFirst` — «Відкрити наявну теку простору»: порожня назва, фокус у теці. */
  function open({ folderFirst = false } = {}) {
    busyForm = null; busyFocus = null;
    const info = deps.spaces();
    const name = needsWelcome(info) && !folderFirst ? t("personalName") : "";
    wz = {
      step: 1, spaceId: null, created: false, busy: false, skipped3: false, seq: 0, refocus: false,
      s1: { name, color: freeColor(info?.spaces), path: folderFirst ? "" : defaultSpacePath(name, "~", deps.takenPaths()),
        pathTouched: folderFirst, folderFirst },
      list: null, failed: null, pick: null, atPick: new Map(),
      cards: [], offs: [], s3failed: null, s3loading: false,
      s4: { title: "", id: "", idTouched: false, source: "empty", from: "", autoTitle: "" },
      taskIds: null,
    };
  }

  function view() {
    const sp = spaceRec();
    return {
      step: wz.step, created: wz.created, busy: wz.busy,
      s1: wz.s1,
      s2: { list: wz.list, failed: wz.failed, pick: wz.pick ?? new Set(), capsError: !!sp?.capabilities?.error, path: sp?.path ?? "" },
      s3: { cards: wz.cards, offs: wz.offs, failed: wz.s3failed, loading: wz.s3loading },
      s4: { ...wz.s4, spaceName: sp?.name ?? wz.s1.name, tasks: Number(sp?.tasks) || 0 },
    };
  }

  /** Значення намальованого кроку — у стан; секрети — у повернену мапу «id поля → значення». */
  function capture(el) {
    const secrets = new Map();
    const a = document.activeElement;
    const focusId = a && el.contains(a) && a.id ? a.id : null;
    const step = painted(el);
    const q = (s) => el.querySelector(s);
    if (step === 1) {
      wz.s1.name = q("#sp-name")?.value ?? wz.s1.name;
      if (!wz.created) wz.s1.path = q("#sp-path")?.value ?? wz.s1.path;
      wz.s1.color = q('input[name="color"]')?.value ?? wz.s1.color;
    } else if (step === 3) {
      for (const card of wz.cards) {
        /* Щойно записана картка: її базис — відповідь сервера (`runOp`), а DOM ще несе набране ДО запису: не читати. */
        if (card.fresh) { delete card.fresh; continue; }
        const root = q(`.wz-card[data-id="${CSS.escape(card.entry.id)}"]`);
        if (!root) continue;
        const cur = readFields(root);
        card.values = cur.values;
        card.erase = cur.erase;
        for (const n of root.querySelectorAll('[data-cn-field][data-type="secret"]')) if (n.value) secrets.set(n.id, n.value);
      }
    } else if (step === 4) {
      wz.s4.title = q("#tf-title")?.value ?? wz.s4.title;
      wz.s4.id = q("#tf-id")?.value ?? wz.s4.id;
      wz.s4.from = q("#wz-from")?.value ?? wz.s4.from;
      wz.s4.source = q('input[name="wz-src"]:checked')?.value ?? wz.s4.source;
    }
    return { secrets, focusId };
  }

  function wire(el) {
    if (wz.step === 1) {
      const form = el.querySelector('form[data-wz-step="1"]');
      if (form) {
        /* Зайнятий крок (запит створення летить, `afterSpaceChange` перемальовує сторінку, чи змінили мову) — теж без peek:
           тека вже створюється, і проводка `new` спитала б сервер про неї й показала б «Цю теку вже додано». */
        wireSpaceDialog(form, { mode: wz.created || wz.busy ? "edit" : "new", peek: deps.peek, taken: deps.takenPaths,
          pathTouched: wz.s1.pathTouched });
      }
    } else if (wz.step === 4) {
      const form = el.querySelector('form[data-wz-step="4"]');
      if (form) {
        wz.taskIds ??= deps.takenTaskIds();
        wireTaskForm(form, { taken: wz.taskIds, idTouched: wz.s4.idTouched });
      }
    }
  }

  /** Повна перемальовка сторінки з тим, що людина вже набрала (секрети — лише властивістю `.value`). */
  function paint() {
    const el = deps.node();
    if (!el || !wz) return;
    const keep = capture(el);
    const top = el.scrollTop;
    el.innerHTML = wizardHTML(view());
    el.scrollTop = top;
    for (const [id, v] of keep.secrets) {
      const n = el.querySelector(`#${CSS.escape(id)}`);
      if (n) n.value = v;
    }
    wire(el);
    if (keep.focusId) el.querySelector(`#${CSS.escape(keep.focusId)}`)?.focus({ preventScroll: true });
  }

  function focusStep() {
    const el = deps.node();
    if (!el || !wz) return;
    if (wz.step === 1 && !wz.created) {
      el.querySelector(wz.s1.folderFirst ? "#sp-path" : "#sp-name")?.focus({ preventScroll: true });
      return;
    }
    el.querySelector("#wz-h")?.focus({ preventScroll: true });
  }

  function go(step) {
    if (!wz) return;
    wz.step = step;
    if (step === 4) wz.taskIds = null;     // свіжий перелік зайнятих id на кожен вхід
    paint();
    /* Новий крок — з верху сторінки: `paint` повертає старий скрол, а заголовок фокусується без прокрутки (`focusStep`) —
       на довгому кроці він лишився б над кадром. */
    if (deps.node()) deps.node().scrollTop = 0;
    focusStep();
    if (step === 2) loadStep2();
    else if (step === 3) loadStep3();
  }

  function exit(msg, back = false) {
    wz = null;
    if (msg) deps.toast(msg);
    deps.exit({ back });
  }
  function spaceGone() { exit(t("wzSpaceGone")); }

  /* ── зайнятість і помилки кроків 1 і 4: на місці, без перемальовки ─────────────────────────────────── */

  /** Повернути фокус, який забрала зайнятість (вимкнений контрол його втрачає). Відмова без поля, яке `showError` могло б
      сфокусувати, інакше лишила б фокус на `body`. */
  function restoreBusyFocus() {
    const was = busyFocus;
    busyFocus = null;
    if (!focusLost()) return;
    const el = deps.node();
    const target = was?.isConnected ? was : ((was?.id && el?.querySelector(`#${CSS.escape(was.id)}`)) || el?.querySelector('.wz [data-a="ok"]'));
    if (target && !target.disabled) target.focus({ preventScroll: true });
  }

  function setBusy(form, on, key) {
    wz.busy = on ? "save" : false;
    if (!on && busyForm && !busyForm.isConnected) {
      /* Сторінку перемалювали, поки летів запит (мова): її намалював зайнятою сам `wizardHTML`, без позначок `wzBusy` —
         правкою вузлів зайнятість не зняти, тож малюємо наново вже без неї (набране `capture` бере з поточних полів). */
      busyForm = null;
      paint();
      restoreBusyFocus();
      return;
    }
    if (on) { busyForm = form; busyFocus = deps.node().contains(document.activeElement) ? document.activeElement : null; }
    else busyForm = null;
    if (on) form.setAttribute("aria-busy", "true");
    else form.removeAttribute("aria-busy");
    const root = deps.node();
    for (const n of root.querySelectorAll(".wz input, .wz button")) {
      if (n.type === "hidden") continue;
      if (on) { if (!n.disabled) { n.disabled = true; n.dataset.wzBusy = "1"; } }
      else if (n.dataset.wzBusy) { n.disabled = false; delete n.dataset.wzBusy; }
    }
    const okBtn = form.querySelector('[data-a="ok"]');
    if (okBtn) {
      if (on) { okBtn.dataset.wzLabel = okBtn.textContent; okBtn.textContent = t(key); }
      else if (okBtn.dataset.wzLabel != null) { okBtn.textContent = okBtn.dataset.wzLabel; delete okBtn.dataset.wzLabel; }
    }
    if (!on) restoreBusyFocus();
  }

  /** Сховати слот помилки кроку (1 чи 4): старий текст не має висіти, коли людина вже виправила поле. */
  function clearError(form) {
    const slot = form?.querySelector("#wz-err");
    if (slot) { slot.textContent = ""; slot.hidden = true; }
  }

  /** Текст помилки в `#wz-err`; поле (`name`) — `aria-invalid` і фокус. Правка поля знімає позначку (`input`). */
  function showError(form, key, field) {
    /* Форму, взяту до запиту, могли відчепити перемальовкою — тоді кажемо про помилку на живій формі цього кроку. */
    const f = form?.isConnected ? form : deps.node()?.querySelector(`form[data-wz-step="${wz?.step}"]`);
    if (!f) return;
    const slot = f.querySelector("#wz-err");
    if (slot) { slot.textContent = t(key); slot.hidden = false; }
    for (const n of f.querySelectorAll('[aria-invalid="true"]')) n.removeAttribute("aria-invalid");
    const n = field ? f.querySelector(`[name="${field}"]`) : null;
    if (n) { n.setAttribute("aria-invalid", "true"); n.focus({ preventScroll: true }); }
  }

  /* ── крок 1 · Простір ─────────────────────────────────────────────────────────────────────────────── */

  async function submit1() {
    const el = deps.node();
    const form = el.querySelector('form[data-wz-step="1"]');
    const mine = wz;
    capture(el);
    clearError(form);
    const name = mine.s1.name.trim();
    if (!name) { showError(form, "spaceErrName", "name"); return; }
    if (mine.created) {
      const cur = spaceRec();
      if (cur && cur.name === name && cur.color === spaceColorToken(mine.s1.color)) { go(2); return; }
      setBusy(form, true, "wzSaving");
      let saved;
      try { saved = await deps.post("/api/space-update", { id: mine.spaceId, name, color: mine.s1.color }); }
      catch (e) {
        if (wz !== mine) return;
        setBusy(form, false);
        if (e?.code === "unknown-space") { spaceGone(); return; }
        showError(form, spaceErrKey(e?.code), spaceErrField(e?.code));
        return;
      }
      /* Сервер уже перейменував — оболонка мусить знати й тоді, коли майстер закрито. Її збій не заклинює сторінку (форма
         лишилась би вимкненою): тост, як у гілці створення. */
      try { deps.afterSpaceEdited(mine.spaceId, saved); } catch (e) { deps.toast(t("errFailed", e?.message ?? "")); }
      if (wz !== mine) return;
      mine.busy = false;
      go(2);
      return;
    }
    setBusy(form, true, "wzCreating");
    let r;
    try { r = await deps.post("/api/space-new", { name, color: mine.s1.color, path: mine.s1.path.trim() }); }
    catch (e) {
      if (wz !== mine) return;
      setBusy(form, false);
      showError(form, spaceErrKey(e?.code), spaceErrField(e?.code));
      return;
    }
    /* Простір УЖЕ створено й зроблено поточним (так робить сервер) — оболонка мусить дізнатись навіть тоді, коли
       майстер тим часом закрили (⌘K): інакше смуга й сервер розійшлися б. */
    mine.spaceId = r.id;
    try { await deps.afterSpaceCreated(); } catch (e) { deps.toast(t("errFailed", e?.message ?? "")); }
    if (wz !== mine) return;
    /* `created` і `busy` — лише тепер: перемальовка у вікні `afterSpaceCreated` (мова) ще малює крок 1 «створення» зайнятим,
       а не режим правки з доступним «Далі». */
    mine.created = true;
    mine.busy = false;
    go(2);
  }

  /* ── крок 2 · Модулі ─────────────────────────────────────────────────────────────────────────────── */

  /** Після «Спробувати ще» кнопка під пальцем зникає (сторінка перемальовується): фокус — на нову «Спробувати ще» (знову
      збій) чи на заголовок кроку, а не на `body`. Лише коли фокус справді втрачено. */
  function afterRetry(mine) {
    if (!mine.refocus) return;
    mine.refocus = false;
    if (!focusLost()) return;
    const el = deps.node();
    (el?.querySelector('[data-wz="retry"]') ?? el?.querySelector("#wz-h"))?.focus({ preventScroll: true });
  }

  async function loadStep2() {
    const mine = wz;
    const seq = ++mine.seq;
    mine.list = null;
    mine.failed = null;
    paint();
    try {
      const r = await deps.api(`/api/modules?space=${encodeURIComponent(mine.spaceId)}`);
      if (wz !== mine || seq !== mine.seq) return;
      mine.list = Array.isArray(r?.modules) ? r.modules : [];
      mine.list2 = mine.list;
      /* Вибір, що пережив «Назад», чистимо від модулів, яких уже нема: радіо показали б «Без модуля», а план — ні. */
      mine.pick = mine.pick ? prunePick(mine.pick, mine.list) : initialPick(mine.list);
      mine.atPick = holdersByRole(mine.list);
    } catch (e) {
      if (wz !== mine || seq !== mine.seq) return;
      if (e?.code === "unknown-space") { spaceGone(); return; }
      mine.failed = { code: e?.code ?? null, message: String(e?.message || e) };
    }
    paint();
    afterRetry(mine);
  }

  function submit2() {
    const skip = !Array.isArray(wz.list) || !!wz.failed || !!spaceRec()?.capabilities?.error;
    wz.skipped3 = skip;
    go(skip ? 4 : 3);
  }

  /* ── крок 3 · Налаштування ───────────────────────────────────────────────────────────────────────── */

  const cardFrom = (entry) => {
    const fields = formFields(entry);
    const init = initialForm(fields);
    return { entry, fields, init, values: init.values, erase: [], errors: {}, result: null };
  };

  async function loadStep3() {
    const mine = wz;
    const seq = ++mine.seq;
    mine.cards = []; mine.offs = []; mine.s3failed = null; mine.s3loading = true;
    paint();
    let list;
    try { list = (await deps.api(`/api/modules?space=${encodeURIComponent(mine.spaceId)}`))?.modules; }
    catch (e) {
      if (wz !== mine || seq !== mine.seq) return;
      if (e?.code === "unknown-space") { spaceGone(); return; }
      mine.s3failed = { code: e?.code ?? null, message: String(e?.message || e) };
      mine.s3loading = false;
      paint();
      afterRetry(mine);
      return;
    }
    if (wz !== mine || seq !== mine.seq) return;
    mine.list = Array.isArray(list) ? list : [];
    /* Вибраний модуль зник між кроками: картки для нього нема, тож назад на крок 2 — він покаже, що лишилось. */
    if (prunePick(mine.pick, mine.list).size !== mine.pick.size) {
      mine.s3loading = false;
      deps.toast(t(refusalView({ code: "unknown-module" }).key));
      go(2);
      return;
    }
    mine.cards = pickedInOrder(mine.list, mine.pick).map(cardFrom);
    /* «Без модуля» + тримачі з помилкою, яких `replace` не вимикає (сервер їх не рахує тримачами) — майстер вимкне їх сам. */
    mine.offs = [...offRows(mine.list, mine.pick), ...errOffRows(mine.list, mine.pick)].map((o) => ({ ...o, result: null }));
    mine.s3loading = false;
    paint();
    afterRetry(mine);
  }

  /** Поля паролів картки — порожні (сервер відповів на її запис). */
  function clearSecrets(id) {
    const root = deps.node()?.querySelector(`.wz-card[data-id="${CSS.escape(id)}"]`);
    for (const n of root?.querySelectorAll('[data-type="secret"]') ?? []) n.value = "";
  }

  /** Чи є на кроці 3 незбережене (змінене поле чи введений секрет). */
  function dirty() {
    if (!wz || wz.step !== 3) return false;
    const el = deps.node();
    if (painted(el) !== 3) return false;
    return wz.cards.some((c) => {
      const root = el.querySelector(`.wz-card[data-id="${CSS.escape(c.entry.id)}"]`);
      return !!root && isDirty(formPatch(c.fields, c.init, readFields(root)));
    });
  }

  /**
   * Один запис плану. `pass` — стан проходу: `written` (id увімкнених без HTTP-помилки; провалена перевірка — теж
   * записано) і `replaced` (що сервер вимкнув заміною, з відповіді `module-enable`). Залежне вимкнення (`op.after`
   * непорожній — тримач звільненої ролі, якого `replace` міг не вимкнути) іде лише після записаної заміни: інакше роль
   * лишилась би без постачальника, а повтор уперся б у «свіжість».
   */
  async function runOp(mine, op, fresh, forms, pass) {
    const card = mine.cards.find((c) => c.entry.id === op.id) ?? null;
    let result;
    if (op.op === "disable" && op.after.length && pass.replaced.has(op.id)) {
      result = { kind: "ok", key: "wzOffDone", detail: "" };
    } else if (op.op === "disable" && op.after.length && !op.after.some((id) => pass.written.has(id))) {
      result = { kind: "refused", key: "wzOffBlocked", detail: "" };
    } else if (op.op === "gone") {
      result = { kind: "refused", ...refusalView({ code: "unknown-module" }) };
    } else if (op.stale.length) {
      const now = holdersByRole(fresh);
      const names = op.stale.flatMap((r) => now.get(r) ?? [])
        .map((id) => modName(fresh.find((e) => e.id === id) ?? { id }));
      result = { kind: "refused", key: "wzStale", detail: [...new Set(names)].join(", ") };
    } else {
      const path = op.op === "enable" ? "/api/module-enable" : op.op === "settings" ? "/api/module-settings" : "/api/module-disable";
      const f = forms.get(op.id);
      const body = op.op === "disable" ? { space: mine.spaceId, id: op.id }
        : writePayload(mine.spaceId, op.id, formPatch(f.fields, f.init, f.cur), op.op === "enable");
      try {
        const r = await deps.post(path, body);
        /* Ролі, які змінив САМ цей прохід (модуль і кого вимкнула заміна): повтор звіряє свіжість по них від нового стану. */
        if (op.op !== "settings") {
          for (const id of [op.id, ...(op.op === "enable" && Array.isArray(r?.replaced) ? r.replaced : [])]) {
            for (const role of fresh.find((e) => e?.id === id)?.roles ?? []) pass.touched.add(role);
          }
        }
        if (op.op === "disable") result = { kind: "ok", key: "wzOffDone", detail: "" };
        else {
          if (op.op === "enable") {
            pass.written.add(op.id);
            /* Кого вимкнула сама заміна — рядки «вимкнеться» отримують результат з відповіді сервера, не з плану. */
            for (const id of Array.isArray(r?.replaced) ? r.replaced : []) {
              pass.replaced.add(id);
              for (const o of mine.offs) if (o.holder.id === id) o.result = { kind: "ok", key: "wzOffDone", detail: "" };
            }
          }
          result = { kind: r?.check?.ok === true ? "ok" : "failed", ...verdictText(r?.check) };
          /* Новий базис картки: збережене вже не «зміна», і стан секрету («задано») — з відповіді. */
          if (card && r?.module) Object.assign(card, cardFrom(r.module), { fresh: true });
        }
      } catch (e) {
        if (e?.code === "unknown-space") return { kind: "gone-space" };
        result = { kind: "refused", ...refusalView(e) };
      }
      clearSecrets(op.id);
    }
    if (card) card.result = result;
    for (const o of mine.offs) if (o.holder.id === op.id) o.result = result;
    paint();
    return result;
  }

  async function submit3() {
    /* Список кроку 3 не прочитався — карток нема, писати нема з чого (форма без картки дала б TypeError): спершу повтор. */
    if (wz.s3failed) { loadStep3(); return; }
    const el = deps.node();
    const mine = wz;
    const keep = capture(el);
    /* Поточні значення картки для моделі: секрети — з локальної мапи (за id поля `wz-f-<картка>-<поле>`). */
    const curOf = (c, i) => ({
      values: c.values, erase: c.erase,
      secrets: Object.fromEntries(c.fields.map((f, j) => [f, j]).filter(([f]) => f.type === "secret")
        .map(([f, j]) => [f.key, keep.secrets.get(`wz-f-${i}-${j}`) ?? ""])),
    });
    let bad = false;
    mine.cards.forEach((c, i) => {
      const miss = missingRequired(c.fields, curOf(c, i));
      c.errors = Object.fromEntries(miss.map((k) => [k, "cnFieldRequired"]));
      if (miss.length) bad = true;
    });
    if (bad) {
      paint();
      deps.node()?.querySelector('.wz [aria-invalid="true"]')?.focus();      // без preventScroll: помилка має опинитись у кадрі
      return;
    }
    const forms = new Map(mine.cards.map((c, i) => [c.entry.id, { fields: c.fields, init: c.init, cur: curOf(c, i) }]));
    mine.busy = "save";
    paint();
    let fresh;
    try { fresh = (await deps.api(`/api/modules?space=${encodeURIComponent(mine.spaceId)}`))?.modules ?? []; }
    catch (e) {
      if (wz !== mine) return;
      if (e?.code === "unknown-space") { spaceGone(); return; }
      /* Нічого не відправлено: картки, набране й секрети лишаються — збій читання не дає права їх губити (`s3failed` лише для
         читання кроку 3). Тост, а «Зберегти» під рукою — повтор шле те саме. */
      mine.busy = false;
      paint();
      deps.toast(t("cnErrLoad"));
      deps.node()?.querySelector('.wz [data-a="ok"]')?.focus();
      return;
    }
    if (wz !== mine) return;
    const ops = writePlan({ list: fresh, pick: mine.pick, forms, atPick: mine.atPick, prevList: mine.list2 });
    const results = [];
    const pass = { written: new Set(), replaced: new Set(), touched: new Set() };
    let changed = false;
    for (const op of ops) {
      if (wz !== mine) break;
      const res = await runOp(mine, op, fresh, forms, pass);
      if (res.kind === "gone-space") { mine.busy = false; spaceGone(); return; }
      results.push(res);
      if (res.kind === "ok" || res.kind === "failed") changed = true;
    }
    /* Знімок кроку 2 для ролей, які змінив сам цей прохід, — на стан після проходу: інакше повтор вважав би власні записи
       «зміною агента» й застряг на свіжості. Ролі, яких прохід не торкався, лишаються зі знімком кроку 2. */
    if (changed && pass.touched.size) {
      try {
        const l = (await deps.api(`/api/modules?space=${encodeURIComponent(mine.spaceId)}`))?.modules;
        if (wz === mine && Array.isArray(l)) {
          const now = holdersByRole(l);
          for (const role of pass.touched) mine.atPick.set(role, now.get(role) ?? []);
        }
      } catch (e) { /* лишаємо знімок кроку 2 */ }
    }
    if (changed) { try { await deps.afterModulesChange(); } catch (e) { /* екран оновиться при наступному вході */ } }
    if (wz !== mine) return;
    mine.busy = false;           // лише тепер: перемальовка в проміжку (мова) має малювати форму зайнятою, а не доступною
    if (allOk(results)) { go(4); return; }
    paint();
    /* Перше поле картки/рядка з відмовою; рядок «вимкнеться» чи картка без полів — сам контейнер (`tabindex="-1"`). */
    const box = deps.node()?.querySelector(".wz-card .cn-res--err, .wz-off .cn-res--err")?.closest(".wz-card, .wz-off");
    (box?.querySelector("input, select, button") ?? box)?.focus();
  }

  /* ── крок 4 · Перша задача ───────────────────────────────────────────────────────────────────────── */

  async function submit4() {
    const el = deps.node();
    const form = el.querySelector('form[data-wz-step="4"]');
    const mine = wz;
    /* Перелік зайнятих id може ще вантажитись: друга відправка в цей проміжок дала б два `task-new` (зайнятість — `setBusy` —
       стає лише ПІСЛЯ перевірки). */
    if (mine.checking) return;
    capture(el);
    clearError(form);
    const vals = { title: mine.s4.title, id: mine.s4.id };
    mine.checking = true;
    let ids;
    try { ids = await Promise.resolve(mine.taskIds ?? []); } catch (e) { ids = []; }
    mine.checking = false;
    if (wz !== mine || mine.step !== 4) return;      // поки перевірявся перелік, людина могла піти «Назад» чи закрити майстер
    const key = taskFormError(vals, ids);
    if (key) { showError(form, key, taskErrField(key)); return; }
    const folder = mine.s4.source === "folder";
    const from = mine.s4.from.trim();
    if (folder && !from) { showError(form, "wzFromRequired", "from"); return; }
    setBusy(form, true, "wzCreating");
    let made;
    try {
      made = await deps.post("/api/task-new", { id: vals.id, title: vals.title.trim(), space: mine.spaceId, ...(folder ? { from } : {}) });
    } catch (e) {
      if (wz !== mine) return;
      setBusy(form, false);
      if (e?.code === "unknown-space") { spaceGone(); return; }
      const k = taskErrKey(e?.code);
      showError(form, k, taskErrField(k));
      return;
    }
    const links = Number(made?.copied?.skipped_links) || 0;
    wz = null;
    if (links) deps.toast(t("wzSkippedLinks", links));
    /* Майстер уже закрито (`wz = null`), а сторінка ще стоїть із вимкненою формою: коли оболонка не змогла відкрити задачу,
       людину не лишаємо на ній — на «Задачі» (задачу створено, вона там є). */
    try { await deps.openTask(made); } catch (e) { deps.toast(t("errFailed", e?.message ?? "")); deps.exit({ back: false }); }
  }

  async function copyPhrase() {
    const text = deps.node()?.querySelector("#wz-phrase")?.textContent ?? "";
    try { await deps.copy(text); deps.toast(t("wzCopied")); } catch (e) { deps.toast(t("wzCopyFailed")); }
  }

  /* ── навігація й вихід ───────────────────────────────────────────────────────────────────────────── */

  async function back() {
    if (!wz || wz.busy) return;
    const mine = wz;
    if (wz.step === 3 && dirty() && !(await askDiscard())) return;
    if (wz !== mine) return;           // питання висіло, а майстер тим часом закрили чи відкрили наново
    go(prevStep(mine.step, mine.skipped3));
  }

  /** «Закрити майстер», «Пропустити», логотип: незбережене кроку 3 — питання; створений простір — тост «готовий». Ще не
      створений (логотип на кроці 1) — те саме, що «Скасувати»: назад, звідки майстер відкрили (спека, «Вихід із майстра»). */
  async function requestExit() {
    if (!wz || wz.busy) return;
    const mine = wz;
    if (dirty() && !(await askDiscard())) return;
    if (wz !== mine) return;           // питання висіло, а майстер тим часом закрили чи відкрили наново (інакше закрили б чужий)
    exit(mine.created ? t("wzReady", spaceRec()?.name ?? mine.s1.name) : null, !mine.created);
  }

  /** «Скасувати» до створення: простору ще нема — назад, звідки прийшли. */
  function cancel() {
    if (!wz || wz.busy || wz.created) return;
    exit(null, true);
  }

  /* ── події сторінки (делегує `wireHome` у `app.js`) ──────────────────────────────────────────────── */

  function click(ev) {
    if (!wz) return;
    const b = ev.target.closest('[data-wz], [data-a="cancel"], [data-cn-dr="erase"]');
    if (!b || b.disabled) return;
    if (b.dataset.cnDr === "erase") { toggleErase(b); return; }
    if (b.dataset.a === "cancel") { cancel(); return; }
    const a = b.dataset.wz;
    if (a === "back") back();
    else if (a === "close" || a === "skip") requestExit();
    else if (a === "retry") { wz.refocus = true; if (wz.step === 3) loadStep3(); else loadStep2(); }
    else if (a === "copy") copyPhrase();
  }

  function submit(ev) {
    ev.preventDefault();
    if (!wz || wz.busy) return;
    const step = Number(ev.target?.dataset?.wzStep);
    if (step !== wz.step) return;
    if (step === 1) submit1();
    else if (step === 2) submit2();
    else if (step === 3) submit3();
    else if (step === 4) submit4();
  }

  /** Поле картки кроку 3: правка знімає й текст «обовʼязкове» (інакше без `aria-invalid` він висів би під полем), і запис у стані. */
  function dropFieldError(n) {
    const errId = `${n.id}-err`;
    document.getElementById(errId)?.remove();
    const ids = (n.getAttribute("aria-describedby") || "").split(/\s+/).filter((x) => x && x !== errId);
    if (ids.length) n.setAttribute("aria-describedby", ids.join(" "));
    else n.removeAttribute("aria-describedby");
    const card = wz.cards.find((c) => c.entry.id === n.closest(".wz-card")?.dataset.id);
    if (card && Object.prototype.hasOwnProperty.call(card.errors, n.dataset.cnField)) delete card.errors[n.dataset.cnField];
  }

  /** `input` і `change` сторінки: позначки «правлено руками», вибір модуля, джерело макета, назва з теки. */
  function input(ev) {
    if (!wz) return;
    const n = ev.target;
    if (n.getAttribute?.("aria-invalid") === "true") {
      n.removeAttribute("aria-invalid");
      clearError(n.closest?.("form"));
      if (n.dataset?.cnField != null && n.id) dropFieldError(n);
    }
    if (ev.type === "input") {
      if (n.id === "sp-path") wz.s1.pathTouched = true;
      else if (n.id === "tf-id") wz.s4.idTouched = n.value !== "";
      else if (n.id === "wz-from") {
        const title = deps.node()?.querySelector("#tf-title");
        if (title && (!title.value.trim() || title.value === wz.s4.autoTitle)) {
          const v = titleFromFolder(n.value);
          title.value = v;
          wz.s4.autoTitle = v;
          title.dispatchEvent(new Event("input", { bubbles: true }));
        }
      }
      return;
    }
    if (n.dataset?.wzPick != null && n.checked) {
      wz.pick = n.value ? pickModule(wz.pick ?? new Set(), wz.list, n.value) : pickNone(wz.pick ?? new Set(), wz.list, n.dataset.role);
      paint();
    } else if (n.name === "wz-src" && n.checked) {
      wz.s4.source = n.value;
      const box = deps.node()?.querySelector("#wz-from-f");
      if (box) box.hidden = n.value !== "folder";
      if (n.value === "folder") deps.node()?.querySelector("#wz-from")?.focus({ preventScroll: true });
    }
  }

  return {
    open, paint, focusStep, requestExit, click, submit, input, dirty,
    reset() { wz = null; busyForm = null; busyFocus = null; },
    active: () => !!wz,
  };
}
