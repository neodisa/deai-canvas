/**
 * Вигляд і мова форми коментатора над макетом: що оболонка віддає коментатору через `host.theme` / `host.labels`.
 *
 * Чистий модуль (жодних DOM-глобалів): його імпортують і Deai (`app.js`), і оболонка превʼю (`ext-shell.js`, їде в
 * публікацію в `SHELL_MODULES`). Один перелік токенів — щоб дві оболонки не розійшлись. Коментатор фільтрує обидва
 * об'єкти сам (білий список ключів, значення без `;{}<>`), тут лише збирання.
 */

/** Токени оболонки, які форма бере в оболонки (мусить збігатись із `THEME_KEYS` коментатора — інакше зайве просто відкинуть). */
export const CMT_THEME_KEYS = [
  "s1", "s2", "s3", "s4", "line", "line2", "hi", "mid", "lo", "dim",
  "sel", "sel-hover", "sel-tint-2", "on-sel", "open", "bad", "local-pin",
];

/** `cs` — `getComputedStyle(document.body)`: токени живуть на `:root` і успадковуються. Порожні пропускаються. */
export function cmtTheme(cs) {
  const o = {};
  for (const k of CMT_THEME_KEYS) {
    const v = String(cs.getPropertyValue("--" + k) || "").trim();
    if (v) o[k] = v;
  }
  return o;
}

/** Підписи форми мовою оболонки: `tr` — її `t()`; шаблони `{tag}`/`{text}`/`{target}`/`{n}` підставляє коментатор. */
export function cmtLabels(tr) {
  return {
    placeholder: tr("cmtFormPh"),
    cancel: tr("cmtFormCancel"),
    submit: tr("cmtFormSubmit"),
    target: tr("cmtFormTarget"),
    quote: tr("cmtFormQuote"),
    area: tr("cmtFormArea"),
    multiTitle: tr("cmtFormMulti"),
    clear: tr("cmtFormClear"),
  };
}
