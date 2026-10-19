/**
 * Спільна основа «золотого знімка ЛІГА» (`tests/legacy-golden.test.mjs`): набір станів і функція, що
 * з них знімає розмітку смуги та дії палітри. Файл НЕ `*.test.mjs` навмисно (як `_sources.mjs`): у
 * прогін окремим файлом без тестів він не потрапляє.
 *
 * Навіщо знімок. Публікація за `capabilities.publish` (модулі 2а, Task 8) розщепила спільне «назовні»
 * на дві умови, а простір ЛІГА мусить лишитись БАЙТ-У-БАЙТ таким, яким був до модулів: його користувачі —
 * єдині, хто сьогодні публікує у Vercel. Перелік id сам такої обіцянки не тримає — не помітить ні
 * підпису, ні атрибута, ні порядку пунктів. Тому еталони лежать ЛІТЕРАЛАМИ у `tests/fixtures/legacy-golden/`,
 * а знімались вони з коду ДО модулів (знято з коду перед Task 8 етапу 2а — стан після Task 7) і звірені з поточним побайтно.
 *
 * Функція приймає модулі ІНЖЕКЦІЄЮ: той самий код знімає еталон і з поточного дерева, і з копії батьківського
 * коміту (так еталон звіряли з минулим, а не з самим собою).
 */

/** Простір ЛІГА в формі відповіді після модулів: інтеграції ввімкнено, публікує зашитий код. Форма 2а (без ключа
 *  `comments`) лишена свідомо: це відповідь сервера, що роль `comments` ще не знає, і ЛІГА з нею мусить лишитись такою
 *  самою (`hasTeamComments`: відсутній ключ = «не знаємо» → за `integrations`). */
export const LIGA = {
  id: "liga", name: "ЛІГА", color: "space-1", integrations: true,
  capabilities: { publish: "legacy", tokens: null },
};

const STATE = (o = {}) => ({
  mode: "layout", view: "grid", vp: "desktop", vpw: "",
  taskId: "LIGA-7003", iterLabel: "Іт.3", iterNote: "Правки",
  hasIteration: true, iterPub: true, iterOnGl: false,
  flowRaw: true, pagesError: "", flowError: "",
  gl: "sync", published: true, pubStale: false, pagePub: true,
  right: null, tasksErr: false, space: LIGA, ...o,
});

/** Стани смуги: закрита; дропдаун публікації в трьох станах; дропдаун GitLab. */
export const BAR_CASES = {
  closed: STATE(),
  "pub-published": STATE({
    openDd: "pub", pw: "1100", pwCustom: true, pwStale: true,
    teams: { channel: "dc/blog", muted: false },
  }),
  "pub-fresh": STATE({
    openDd: "pub", published: false, iterPub: false, pw: "1100", pwUngated: 3, teams: null,
  }),
  "pub-teams-muted": STATE({
    openDd: "pub", pw: "4242", teams: { channel: "dc/blog", muted: true, muted_by: "k:0123456789ab", mine: false },
  }),
  "gl-behind": STATE({ openDd: "gl", gl: "behind", iterOnGl: true }),
};

/** Стани палітри: GitLab відстає, «не підключено», збігається (+ не опубліковано). */
export const PALETTE_CASES = {
  behind: { gl: "behind" },
  off: { gl: "off" },
  "sync-unpublished": { gl: "sync", published: false },
};

const PALETTE = (o) => ({
  mode: "layout", view: "grid", hasIteration: true,
  pagesError: "", flowRaw: true, flowError: "",
  published: true, iterPub: true, pagePub: true, pickedPage: "main",
  gl: "sync", iterLabel: "Іт.3",
  shots: { have: 3, stale: 0, total: 3, running: false, bad: false, done: 0 },
  lang: "uk", commentMode: "local",
  space: { id: LIGA.id, integrations: true, capabilities: LIGA.capabilities },
  ...o,
});

/** `{bar: {назва: html}, palette: {назва: [дії]}}` з переданих модулів. */
export function snapshot({ barModel, barHTML, paletteActions }) {
  const bar = {};
  for (const [name, st] of Object.entries(BAR_CASES)) bar[name] = barHTML(barModel(st), st);
  const palette = {};
  for (const [name, o] of Object.entries(PALETTE_CASES)) {
    // через JSON: у файлі лежить те, що серіалізується, без `undefined`-полів
    palette[name] = JSON.parse(JSON.stringify(paletteActions(PALETTE(o))));
  }
  return { bar, palette };
}
