/**
 * Чистий перегляд макета (fb-01102026-7f7b6d): прибрати оболонку інструмента з
 * екрана й повернути — у робочому канвасі (`app.js`) і в зовнішньому превʼю
 * (`ext-shell.js`). Мета — подивитись на макет як на продукт, без смуги, панелей
 * і пінів (рішення власника 06.10.2026: пін теж ховається).
 *
 * Обидві оболонки мають ті самі класи (`bar-mount`, `pages-panel`, `cv-stage`,
 * рамка `#frame`), тому ховає один клас на `<html>` (`cv-clean`, правила — у
 * `styles.css`), а не дві копії логіки.
 *
 * ⛔ Обробник клавіш оболонки живе в БАТЬКІВСЬКОМУ документі, а в чистому режимі
 * людина клікає по макету — фокус переходить у рамку, і keydown іде вже туди.
 * Тому (1) у документ рамки вішаємо свій слухач того самого акорду (same-origin,
 * як інспектор), і (2) маленька кнопка «показати інтерфейс» є завжди — запасний
 * вихід, що не залежить від фокусу. Кнопка живе в батьківському документі, тож
 * у кадри зʼємки й у «В Figma» (документ рамки) не потрапляє.
 *
 * Коментатор — окремий продукт: у ньому нічого не міняємо, а ховаємо його хост
 * ззовні (`[data-comment-layer]` у документі рамки) і повертаємо як було.
 *
 * Модуль не знає мови: підписи приходять готовими (`t()` — у викликача), бо
 * кирилиці поза `i18n.js` бути не може (`tests/i18n-literals.test.mjs`).
 */
export const CLEAN_CLASS = "cv-clean";

/** ⇧⌘\ (⇧⌃\ поза macOS). `code`, а не `key`: із Shift `\` дає `|`. */
export function isCleanChord(ev) {
  return !!((ev.metaKey || ev.ctrlKey) && ev.shiftKey && !ev.altKey && ev.code === "Backslash");
}

/**
 * Документ рамки: сховати/повернути хост коментатора і (один раз на документ)
 * повісити слухач акорду — новий документ після перезавантаження рамки дістане
 * свій. `onChord` — що робити на акорді (перемкнути режим).
 */
export function syncFrame(frame, on, onChord) {
  let d;
  try { d = frame && frame.contentDocument; } catch (e) { return; }
  if (!d) return;
  /* Правило-стиль, а не `style.display` на хості: хост коментатора створюється
     ПІСЛЯ події load рамки, тож хост «на зараз» міг ще не існувати, а після
     перезавантаження зʼявлявся видимим (ревʼю 1.51). Стиль у документі діє й
     на хост, що зʼявиться пізніше. */
  let st = d.getElementById("dc-clean-style");
  if (on && !st && (d.head || d.documentElement)) {
    st = d.createElement("style");
    st.id = "dc-clean-style";
    st.textContent = "[data-comment-layer]{display:none!important}";
    (d.head || d.documentElement).appendChild(st);
  } else if (!on && st) {
    st.remove();
  }
  if (onChord && !d.__dcCleanChord) {
    d.__dcCleanChord = true;
    d.addEventListener("keydown", (ev) => {
      if (!isCleanChord(ev)) return;
      ev.preventDefault();
      onChord();
    });
  }
}

/**
 * Застосувати стан: клас на `<html>`, кнопка повернення, документ рамки.
 * `opts`: `{ label, title, onExit, onChord }` — підписи вже перекладені.
 */
export function applyClean(doc, frame, on, opts) {
  doc.documentElement.classList.toggle(CLEAN_CLASS, on);
  let btn = doc.getElementById("cv-unclean");
  if (on && !btn) {
    btn = doc.createElement("button");
    btn.id = "cv-unclean";
    btn.type = "button";
    btn.className = "cv-unclean";
    btn.setAttribute("data-h2d-ignore", "true");
    btn.textContent = opts.label;
    btn.title = opts.title || opts.label;
    btn.addEventListener("click", () => opts.onExit());
    doc.body.appendChild(btn);
  } else if (!on && btn) {
    btn.remove();
  }
  syncFrame(frame, on, opts.onChord);
}
