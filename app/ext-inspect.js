/**
 * Інспектор в ОПУБЛІКОВАНОМУ превʼю (0.32.0, етап Ж): права панель `#insp-panel` оболонки превʼю — та сама розмітка, що в Deai
 * (`inspectHTML` → `panelHTML`), але ЛИШЕ ДЛЯ ПЕРЕГЛЯДУ (`readonly: true`): значення текстом, чипи токенів зі знімка, жодного
 * тюнера, «Надіслати AI», «до токена», скрабу, «+» й перемикача сторін.
 *
 * Сам оверлей живе в документі макета (`CanvasInspector`, `shell/vendor/inspector.js`) — і Alt (відстані), Esc/↵ (батько/
 * дочірній), ← → (сусід), I у рамці він обробляє СВОЇМИ слухачами. Тут — лише проводка, та сама, що `app.js` у Deai: `setChrome`,
 * `setLabels`, `yieldEsc`, `onChange` → перемальовка панелі, і ті самі клавіші, коли фокус в ОБОЛОНЦІ, а не в рамці.
 *
 * Чого тут нема свідомо: тюнера (`reapplyTune`), будь-яких запитів (знімок токенів оверлей читає сам, файлом збірки) і запису
 * в макет. Модуль їде в публічне превʼю байт у байт, тож тягне лише чисті модулі (`shell-inspect.js`, `insp-model.js`).
 */
import { buildModel } from "./insp-model.js";
import { t } from "./i18n.js";
import { inspectHTML } from "./shell-inspect.js";

/** Поле вводу чи contenteditable: клавіші оболонки тоді не наші (ті самі правила, що в `ext-comments.js` і `app.js`). */
function typingIn(ev, doc) {
  const isEd = (n) => !!n && n.nodeType === 1 && (/^(input|textarea|select)$/i.test(n.localName || "") || !!n.isContentEditable);
  const o = (typeof ev.composedPath === "function" && ev.composedPath()[0]) || ev.target;
  let a = null;
  try {
    a = doc?.activeElement || null;
    while (a && a.shadowRoot && a.shadowRoot.activeElement) a = a.shadowRoot.activeElement;
  } catch (e) { a = null; }
  return isEd(o) || isEd(a);
}

/** Модальний шар оболонки (діалог імені, питання, «Копіювати посилання»): Esc і клавіші драбини тоді його. */
const modalOpen = () => !!document.querySelector(".cv-ask-scrim, .cv-ask-pop");

/**
 * Контролер панелі. `frame` — iframe з макета; `mount` — `#insp-panel`; `onChange()` — оболонка перемальовує острівець
 * (натиснута кнопка, наявність кнопки); `onOn()` — інспектор ЩОЙНО ввімкнувся (звідки б не було: кнопка, I, I у рамці) —
 * оболонка гасить коментарі; `canUse()` — чи можна інспектору бути ввімкненим зараз (не чистий перегляд).
 */
export function createExtInspect({ frame, mount, onChange = () => {}, onOn = () => {}, canUse = () => true }) {
  const st = { active: true, has: false };
  mount.setAttribute("aria-label", t("inspector"));

  /** Оверлей рамки або `null`: рамка ще вантажиться, чужий документ, пісочниця (cross-origin кидає). */
  const api = () => {
    try { return (frame.contentWindow && frame.contentWindow.CanvasInspector) || null; } catch (e) { return null; }
  };
  const isOn = () => !!(st.active && api() && api().on);

  function paint() {
    const a = api();
    const on = !!(st.active && a && a.on);
    let model = null;
    if (on) {
      let rep = null;
      try { rep = a.report(); } catch (e) { rep = null; }
      model = rep ? buildModel(rep, { edits: {}, sides: false }) : null;
    }
    const html = inspectHTML({ shellMode: "layout", on, model, readonly: true });
    /* Прокрутку тіла знімаємо ДО перезапису й вертаємо після: пінують кліком, і звіт перечитується вдруге, коли курсор зійде. */
    const top = mount.querySelector(".insp-body")?.scrollTop || 0;
    mount.hidden = !html;
    document.body.classList.toggle("with-insp", !!html);
    mount.innerHTML = html;
    const body = mount.querySelector(".insp-body");
    if (body && top) body.scrollTop = top;
    onChange();
  }

  /** Увімкнути/вимкнути оверлей. Ввімкнення при чистому перегляді чи в «Огляді» — ні. */
  function setOn(on) {
    const a = api();
    if (!a) return;
    on = !!on;
    if (on && !(st.active && canUse())) return;
    if (a.on === on) { paint(); return; }
    a.set(on);                    // `onChange` оверлея (нижче) сам перемалює панель і покличе `onOn`
    paint();
  }

  /** Рамка завантажила документ: новий документ = новий екземпляр оверлея, тож проводимо його заново (як `app.js` у Deai). */
  function onFrameLoad() {
    const a = api();
    st.has = !!a;
    if (a) {
      a.setChrome(false);                                   // власну кнопку оверлея ховаємо: керуємо з острівця
      a.setLabels({ inspector: t("inspector") });
      a.yieldEsc = () => modalOpen();                       // Esc поступається відкритому питанню/формі оболонки
      a.onChange = (on) => {
        if (on && !(st.active && canUse())) { try { a.set(false); } catch (e) { /* рамка пішла */ } return; }
        if (on) onOn();
        paint();
      };
    }
    paint();
  }

  /** Клавіші, коли фокус в ОБОЛОНЦІ: I — перемикач, Alt/Esc/↵/←→ — драбина оверлея (одна логіка з `_onKey` рамки). */
  function shellKey(ev) {
    if (ev.isComposing || ev.defaultPrevented || ev.metaKey || ev.ctrlKey) return;
    if (!st.active || !canUse() || modalOpen() || typingIn(ev, document)) return;
    const a = api();
    if (!a) return;
    if (!ev.altKey && !ev.shiftKey && !ev.repeat && ((ev.key || "").toLowerCase() === "i" || ev.code === "KeyI")) {
      ev.preventDefault();
      setOn(!a.on);
      return;
    }
    if (!a.on) return;
    if (ev.key === "Alt") { a.setAlt(true); return; }
    if (ev.shiftKey) return;                  // Shift+←/→ — виділення тексту, не навігація
    if (ev.target !== document.body) return;  // на кнопці чи в дереві стрілки й Enter належать їм
    if (a.handleKey(ev.key, { alt: ev.altKey })) ev.preventDefault();
  }

  const actions = {
    inspector: () => setOn(!api()?.on),
    /* Крихта предка: індекс резолвить САМ оверлей (`pinAt`) — масив предків живий лише там. */
    inspcrumb: (val) => { api()?.pinAt(val); paint(); },
    /* «N поза ДС»: докрутити до наступного бурштинового поля по колу (у перегляді полів вводу нема — лише прокрутка). */
    inspnextoff: () => {
      const list = [...mount.querySelectorAll(".insp-f[data-off]")];
      if (!list.length) return;
      st.offAt = ((st.offAt ?? -1) + 1) % list.length;
      list[st.offAt].scrollIntoView?.({ block: "nearest" });
    },
  };

  return {
    actions, onFrameLoad, paint, shellKey, setOn,
    isOn,
    /** Чи є в рамці оверлей (для кнопки острівця): документ без нього — кнопки нема. */
    has: () => st.has && !!api(),
    /** Вид без живого макета («Огляд» — кадри-знімки): панель ховаємо, оверлей вимикаємо. */
    setActive(on) {
      on = !!on;
      if (st.active === on) return;
      st.active = on;
      if (!on) { try { const a = api(); if (a && a.on) a.set(false); } catch (e) { /* рамка пішла */ } }
      paint();
    },
    /** Alt відпущено чи вікно втратило фокус — лінії відстаней гаснуть. */
    altOff() { try { api()?.setAlt(false); } catch (e) { /* рамка пішла */ } },
  };
}
