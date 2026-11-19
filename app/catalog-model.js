/**
 * Каталог «Додати модуль» і «Свій модуль» (етап Е, 0.31.0; спека `docs/superpowers/specs/2026-11-19-settings-e-design.md`, §3).
 * Чисті функції — ні DOM, ні `t()`: групи рядків каталогу й текст запиту агенту. Розмітку малює `catalog-view.js`.
 */
import { DICT } from "./i18n.js";
import { ROLE_ORDER, roleHolders } from "./connections-model.js";
import { gridEntries } from "./modules-grid.js";

const valid = (e) => e && typeof e === "object" && typeof e.id === "string";
const firstRole = (e) => (Array.isArray(e.roles) && typeof e.roles[0] === "string" ? e.roles[0] : "");

/**
 * Групи каталогу: вбудовані модулі, яких НЕМА в сітці (тобто вимкнені), за роллю — у порядку `ROLE_ORDER`, далі інші ролі за
 * абеткою, модулі без ролі — останніми. Рядок: `{id, entry, replaces}` — `replaces` — назви модулів, що тримають ролі цього
 * модуля зараз (`roleHolders`: увімкнені, не `missing`), одним рядком через кому, або `null`, коли роль вільна. Назву
 * тримача дає `nameOf(entry)` (екран передає `modName`: мова інтерфейсу); типово — `name`/`id` запису.
 * ⛔ Свій модуль простору в каталог не потрапляє ніколи: `gridEntries` бере ВСІ свої (довіра й увімкнення — на його картці).
 */
export function catalogGroups(list, nameOf = (e) => String(e?.name || e?.id || "")) {
  const all = (Array.isArray(list) ? list : []).filter(valid);
  const inGrid = new Set(gridEntries(all));
  const rows = all.filter((e) => !inGrid.has(e));
  const named = [...new Set(rows.map(firstRole))].filter((r) => r && !ROLE_ORDER.includes(r)).sort();
  const order = [...ROLE_ORDER, ...named, ""];
  return order.map((role) => ({
    role,
    rows: rows.filter((e) => firstRole(e) === role).map((entry) => {
      const holders = roleHolders(entry, all);
      return { id: entry.id, entry, replaces: holders.length ? holders.map(nameOf).join(", ") : null };
    }),
  })).filter((g) => g.rows.length);
}

/**
 * Запит агенту для «Свого модуля» мовою інтерфейсу (`lang`): імʼя й тека простору, абсолютний шлях до інструкції ЦІЄЇ
 * установки Deai, що має робити модуль, і заборона довіряти самому. Порожнє `what` — нейтральна підстановка. Тексти — у словнику
 * (`ownPrompt`, `ownPromptWhat`): сюди їх не копіюємо (`tests/i18n-literals.test.mjs`).
 */
export function ownPrompt({ space = "", folder = "", authoring = "", what = "", lang = "uk" } = {}) {
  const d = DICT[lang] ?? DICT.uk;
  const w = String(what ?? "").trim() || d.ownPromptWhat;
  return d.ownPrompt(String(space ?? ""), String(folder ?? ""), String(authoring ?? ""), w);
}
