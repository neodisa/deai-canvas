/**
 * Статус Claude поза смугою (12.10.2026): острівець унизу робочої області й бейдж
 * на іконці встановленого застосунку (Dock / панель задач). Модуль — чисті функції;
 * опит `/api/claude-status`, вузол `#claude-hud` і `navigator` — в `app.js`.
 *
 * Правда одна — серцебиття з TTL на сервері (`serve.claude_view`). Тут нічого не
 * «гасимо» самі: `state` порожній — острівця немає, бейдж знято.
 *
 * Кириличних рядкових літералів тут бути не може (`tests/i18n-literals.test.mjs`): тексти — через `t()`.
 */
import { t } from "./i18n.js";

const STATES = ["working", "waiting", "blocked", "done"];

/** Підпис острівця з відповіді сервера або `null` (серцебиття згасло / ще не було).
 *  Вік — лише в «працює»: «працює · 2 хв тому» чесніше за голе «працює», коли довга
 *  команда йде без жодного інструменту; у решти станів вік нічого не додає.
 *  Нотатка (`note`) в острівець не йде: він клікопрозорий (`pointer-events: none`), тож
 *  підказка-`title` ніколи б не показалась, а власник обрав короткий острівець.
 *  Рядки — звичайний текст, НЕ HTML: у DOM — лише через `textContent`, ніколи через
 *  `innerHTML`. */
export function islandParts(view) {
  if (!view || !view.state) return null;
  const state = STATES.includes(view.state) ? view.state : "working";
  const n = Number(view.age_s);
  const ageS = Number.isFinite(n) ? Math.max(0, Math.floor(n)) : 0;
  const label = state === "working" ? t("claudeWorking") : t(`claude_${state}`);
  const age = state === "working"
    ? (ageS < 60 ? t("ageSec", ageS) : t("ageMin", Math.floor(ageS / 60)))
    : "";
  return { state, label, age };
}

/** Порожній острівець. `app.js` заповнює його НА МІСЦІ (не перестворює): жива область
 *  — постійний `#claude-hud`, і вузол, народжений на кожен опит, оголошувався б щоразу.
 *  Вік — `aria-hidden`: він міняється кожні 5 с, читач екрана бубонів би безкінечно. */
export const ISLAND_SHELL = '<div class="claude-island"><span class="claude-dot"></span>'
  + '<span class="lbl-claude"></span><span class="claude-age" aria-hidden="true"></span></div>';

/** Вид бейджа: `"dot"` — Claude працює (не чекай), `"one"` — потрібен ти (чекає чи
 *  заблоковано), `"none"` — нічого. Невідомий стан — як «працює», той самий вибір, що в
 *  `islandParts`: острівець і бейдж не сміють казати різне. */
export function badgeFor(view) {
  const st = view && view.state;
  if (!st || st === "done") return "none";
  if (st === "waiting" || st === "blocked") return "one";
  return "dot";
}

/** Застосувати бейдж. ⛔ Крапка — `setAppBadge()` БЕЗ аргументу: `setAppBadge(0)` за
 *  специфікацією Badging API бейдж ЗНІМАЄ. API немає (звичайна вкладка, Firefox,
 *  Linux) — тихо нічого; збій — ковтаємо: бейдж підказка, не причина ламати опит.
 *  Будь-який інший `kind` — як `"none"`: невідоме не сміє лишити бейдж висіти. */
export function applyBadge(nav, kind) {
  if (!nav || typeof nav.setAppBadge !== "function") return;
  let p;
  try {
    if (kind === "dot") p = nav.setAppBadge();
    else if (kind === "one") p = nav.setAppBadge(1);
    else p = typeof nav.clearAppBadge === "function" ? nav.clearAppBadge() : nav.setAppBadge(0);
  } catch (e) {
    return;
  }
  if (p && typeof p.catch === "function") p.catch(() => {});
}
