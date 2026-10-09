/**
 * Один SVG-набір іконок замість того, що досі жило в смузі інструмента:
 * `＋ ⊞ ▢ ◎ ⇢ ▦ ⋯ 🔗 📄 📁 ☁ ● ↑ ⚠ ‹ ›` — емодзі, геометричні гліфи,
 * типографські стрілки й юнікод-каретки впереміш. Кожен новий контрол
 * приносив свій знак, бо однаковий вибір ніхто не фіксував — тепер це
 * фіксовано тут: 16px, stroke-width 1.7, currentColor, круглі закінчення.
 * Форми не намальовані наново — витягнуті скриптом (Task 6 Step 3) із
 * затвердженого прототипу `docs/proto/shell.html`, секція «ОДИН НАБІР ІКОН».
 *
 * `ICONS` — мапа імʼя → розмітка `<symbol>`, зібрані разом у рядок `SPRITE`
 * (один `<svg><defs>` на всю сторінку, Task 7 вставляє його в `index.html`).
 * `ico(name)` малює `<use>` на потрібний symbol.
 *
 * Чому невідоме імʼя кидає, а не малює порожнечу: одрук на кшталт
 * `ico('inspekt')` замість `ico('inspect')` в іншому підході мовчки лишив би
 * порожній квадрат 16×16 у темній смузі — таку порожнечу не помічають, поки
 * хтось не придивиться. Виняток видно на першому рендері. Тест
 * `tests/icons.test.mjs` додатково вичитує всі виклики `ico('…')` з коду
 * застосунку і звіряє зі спрайтом статично, за патерном
 * `tests/i18n-keys.test.mjs` для `t('…')`.
 */
export const ICONS = {
  task: `<symbol id="i-task" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <rect x="2.5" y="7" width="19" height="13" rx="2.5"/><path d="M9 7V5.5A1.5 1.5 0 0 1 10.5 4h3A1.5 1.5 0 0 1 15 5.5V7"/><path d="M2.5 12.5h19"/></symbol>`,
  iter: `<symbol id="i-iter" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12 3.5 21 8l-9 4.5L3 8z"/><path d="M3 12.5l9 4.5 9-4.5"/><path d="M3 17l9 4.5 9-4.5"/></symbol>`,
  page: `<symbol id="i-page" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/></symbol>`,
  folder: `<symbol id="i-folder" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <path d="M3 7.5A2 2 0 0 1 5 5.5h3.6a2 2 0 0 1 1.7 1l.7 1.2H19a2 2 0 0 1 2 2v7.8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></symbol>`,
  folderplus: `<symbol id="i-folderplus" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <path d="M3 7.5A2 2 0 0 1 5 5.5h3.6a2 2 0 0 1 1.7 1l.7 1.2H19a2 2 0 0 1 2 2v7.8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M12 11v5"/><path d="M9.5 13.5h5"/></symbol>`,
  state: `<symbol id="i-state" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <rect x="4" y="4" width="16" height="16" rx="3" stroke-dasharray="3.4 3"/><path d="M9.5 12h5"/></symbol>`,
  layout: `<symbol id="i-layout" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <rect x="3" y="4" width="18" height="16" rx="2.5"/><path d="M3 8.5h18"/></symbol>`,
  overview: `<symbol id="i-overview" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <rect x="3.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.5"/>
  <rect x="3.5" y="13.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.5"/></symbol>`,
  grid: `<symbol id="i-grid" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <rect x="3.5" y="3.5" width="17" height="17" rx="2.5"/><path d="M3.5 9.5h17M3.5 15.5h17M9.5 3.5v17M15.5 3.5v17"/></symbol>`,
  flow: `<symbol id="i-flow" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="5.5" cy="12" r="2.5"/><circle cx="18.5" cy="6" r="2.5"/><circle cx="18.5" cy="18" r="2.5"/>
  <path d="M8 11 16 7M8 13l8 4"/></symbol>`,
  desktop: `<symbol id="i-desktop" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <rect x="2.5" y="4" width="19" height="12.5" rx="2"/><path d="M8.5 20h7M12 16.5V20"/></symbol>`,
  tablet: `<symbol id="i-tablet" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <rect x="5" y="2.5" width="14" height="19" rx="2.5"/><path d="M11 18.5h2"/></symbol>`,
  mobile: `<symbol id="i-mobile" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <rect x="7" y="2.5" width="10" height="19" rx="2.5"/><path d="M11 18.6h2"/></symbol>`,
  inspect: `<symbol id="i-inspect" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="4"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3"/></symbol>`,
  ruler: `<symbol id="i-ruler" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <rect x="2" y="8" width="20" height="8" rx="2" transform="rotate(-45 12 12)"/>
  <path d="M9 9.5l1.5 1.5M12 6.5l1.5 1.5M15 3.5 16.5 5"/></symbol>`,
  /* Вкладка «Тюнер» (Task 15). Дві повзунки з ручками на РІЗНИХ позиціях —
     саме це відрізняє «крутилку» від «налаштувань»: однакові позиції читались
     би як два перемикачі. Родич `ruler` за вагою штриха, бо стоять вони в
     одному сегменті й мусять важити однаково. */
  sliders: `<symbol id="i-sliders" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <path d="M4 8h5M13 8h7M4 16h11M19 16h1"/>
  <circle cx="11" cy="8" r="2"/><circle cx="17" cy="16" r="2"/></symbol>`,
  comment: `<symbol id="i-comment" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <path d="M20.5 12.5a7.5 7.5 0 0 1-7.5 7.5 8 8 0 0 1-3.2-.65L4.5 21l1.3-4.3A7.5 7.5 0 0 1 13 4.5a7.5 7.5 0 0 1 7.5 8z"/></symbol>`,
  cloud: `<symbol id="i-cloud" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <path d="M17.5 18.5H7a4.5 4.5 0 0 1-.6-8.96A6 6 0 0 1 18 10.2a4.15 4.15 0 0 1-.5 8.3z"/></symbol>`,
  up: `<symbol id="i-up" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12 20V4M12 4l-6 6M12 4l6 6"/></symbol>`,
  down: `<symbol id="i-down" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12 4v16M12 20l-6-6M12 20l6-6"/></symbol>`,
  /* «Встановити як застосунок» (PWA): стрілка в лоток. Не `down` — той уже
     означає «підтягнути з GitLab» (`glpull`), і два різні дії під одним
     знаком у ⌘K читались би як одна. */
  download: `<symbol id="i-download" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12 4v10M8 10.5l4 4 4-4"/><path d="M4.5 15.5v2.5a1.5 1.5 0 0 0 1.5 1.5h12a1.5 1.5 0 0 0 1.5-1.5v-2.5"/></symbol>`,
  ext: `<symbol id="i-ext" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <path d="M14 4h6v6"/><path d="M20 4 11 13"/><path d="M18 14.5V18a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h3.5"/></symbol>`,
  link: `<symbol id="i-link" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <path d="M9.5 14.5a4 4 0 0 1 0-5.66l2.83-2.83a4 4 0 0 1 5.66 5.66l-1.42 1.41"/>
  <path d="M14.5 9.5a4 4 0 0 1 0 5.66l-2.83 2.83a4 4 0 0 1-5.66-5.66l1.42-1.41"/></symbol>`,
  plus: `<symbol id="i-plus" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12 5v14M5 12h14"/></symbol>`,
  dots: `<symbol id="i-dots" viewBox="0 0 24 24" fill="currentColor" stroke="none">
  <circle cx="5.5" cy="12" r="1.7"/><circle cx="12" cy="12" r="1.7"/><circle cx="18.5" cy="12" r="1.7"/></symbol>`,
  chevdown: `<symbol id="i-chevdown" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
  <path d="M6 9.5l6 6 6-6"/></symbol>`,
  chevright: `<symbol id="i-chevright" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
  <path d="M9.5 6l6 6-6 6"/></symbol>`,
  chevleft: `<symbol id="i-chevleft" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
  <path d="M14.5 6l-6 6 6 6"/></symbol>`,
  camera: `<symbol id="i-camera" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <path d="M3 8.5A2 2 0 0 1 5 6.5h1.8l1-1.7a1.5 1.5 0 0 1 1.3-.8h5.8a1.5 1.5 0 0 1 1.3.8l1 1.7H19a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
  <circle cx="12" cy="12.5" r="3.2"/></symbol>`,
  refresh: `<symbol id="i-refresh" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <path d="M20 12a8 8 0 1 1-2.6-5.9"/><path d="M20 4.5V10h-5.4"/></symbol>`,
  stop: `<symbol id="i-stop" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <rect x="6" y="6" width="12" height="12" rx="2"/></symbol>`,
  lock: `<symbol id="i-lock" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <rect x="5" y="10.5" width="14" height="9.5" rx="2"/><path d="M8.5 10.5V7.5a3.5 3.5 0 0 1 7 0v3"/></symbol>`,
  warn: `<symbol id="i-warn" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12 4.2 21 19.5H3z"/><path d="M12 9.5v4.2M12 16.6v.1"/></symbol>`,
  check: `<symbol id="i-check" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M4.5 12.5l5 5L19.5 7"/></symbol>`,
  x: `<symbol id="i-x" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
  <path d="M6 6l12 12M18 6 6 18"/></symbol>`,
  search: `<symbol id="i-search" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/></symbol>`,
  help: `<symbol id="i-help" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="8.5"/><path d="M9.6 9.4a2.5 2.5 0 1 1 3.4 2.32c-.6.25-1 .84-1 1.5v.28"/><path d="M12 16.8v.1"/></symbol>`,
  panel: `<symbol id="i-panel" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <rect x="3" y="4" width="18" height="16" rx="2.5"/><path d="M9.5 4v16"/></symbol>`,
  pencil: `<symbol id="i-pencil" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <path d="M4 20h4l10.5-10.5a2.12 2.12 0 0 0-3-3L5 17z"/><path d="M14.5 5.5 18.5 9.5"/></symbol>`,
  copy: `<symbol id="i-copy" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <rect x="8.5" y="8.5" width="12" height="12" rx="2.2"/><path d="M15.5 8.5V5.7a2.2 2.2 0 0 0-2.2-2.2H5.7A2.2 2.2 0 0 0 3.5 5.7v7.6a2.2 2.2 0 0 0 2.2 2.2H8.5"/></symbol>`,
  trash: `<symbol id="i-trash" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <path d="M4.5 7h15M9.5 7V4.8A1.3 1.3 0 0 1 10.8 3.5h2.4A1.3 1.3 0 0 1 14.5 4.8V7"/>
  <path d="M6.5 7l.8 12.2A1.8 1.8 0 0 0 9.1 21h5.8a1.8 1.8 0 0 0 1.8-1.8L17.5 7"/></symbol>`,
  eye: `<symbol id="i-eye" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/></symbol>`,
  dot: `<symbol id="i-dot" viewBox="0 0 24 24" fill="currentColor" stroke="none">
  <circle cx="12" cy="12" r="4.5"/></symbol>`,
  globe: `<symbol id="i-globe" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17"/><path d="M12 3.5c2.4 2.3 3.6 5.1 3.6 8.5S14.4 18.2 12 20.5c-2.4-2.3-3.6-5.1-3.6-8.5S9.6 5.8 12 3.5z"/></symbol>`,
  /* Гліф Figma (T-41, кнопка «В Figma») — п'ять фігур знака, намальованих тим
     самим штрихом, що й решта спрайта, а не кольоровий логотип: у смузі
     іконки однотонні й беруть колір з `currentColor`. */
  figma: `<symbol id="i-figma" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12 3H9a3 3 0 0 0 0 6h3zM12 3h3a3 3 0 0 1 0 6h-3zM12 9H9a3 3 0 0 0 0 6h3z"/>
  <circle cx="15" cy="12" r="3"/><path d="M12 15H9a3 3 0 1 0 3 3z"/></symbol>`,
  lang: `<symbol id="i-lang" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <path d="M3.5 5.5h8M7.5 5.5v-2M9.8 5.5c0 4-2.6 7.2-6.3 8.5"/><path d="M4.5 9.8c1.3 2.5 3.4 4 6 4.7"/>
  <path d="M12.5 20.5l4-11 4 11M14 17h5"/></symbol>`,
};

export const SPRITE = `<svg width="0" height="0" style="position:absolute"
  aria-hidden="true"><defs>${Object.values(ICONS).join("")}</defs></svg>`;

export function ico(name, size = 16, cls = "ico") {
  if (!ICONS[name]) throw new Error(`icons: немає іконки «${name}»`);
  return `<svg class="${cls}" width="${size}" height="${size}" aria-hidden="true"`
    + `><use href="#i-${name}"/></svg>`;
}
