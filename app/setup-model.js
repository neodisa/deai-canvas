/**
 * «Перший запуск» (0.33.0): чисті функції станів — ні DOM, ні мережі, ні `t()`. Повертають ІМЕНА ключів словника й дані;
 * розмітку робить `first-run.js` (і `shell-panel.js`, `connections-view.js`, `bar-model.js` для своїх місць).
 */

/** Блок «Кадри» за `shots` з `GET /api/setup`: `{lineKey, whyKey, command}` — знімати нема чим; `null` — можна (ok,
    unknown, ще не питали). `no-playwright` і `no-browser` лікує одна й та сама команда, тож і текст один. */
export function shotsBlock(setupShots) {
  const st = setupShots?.state;
  if (st === "no-playwright" || st === "no-browser") {
    return { lineKey: "frShotsNoBrowser", whyKey: "frShotsNoBrowserWhy", command: setupShots.command || "" };
  }
  if (st === "no-node") return { lineKey: "frShotsNoNode", whyKey: "frShotsNoNodeWhy", command: "" };
  return null;
}

/** Рядок «Claude Code» розділу AGENTS.md за `claude` з `GET /api/agents-md`; `null` — стану нема (старий сервер). */
export function claudeRow(claude) {
  switch (claude?.state) {
    case "ok": return { icon: "check", tone: "ok", textKey: "frClaudeOk", connect: false };
    case "missing": return { icon: "warn", tone: "warn", textKey: "frClaudeMissing", connect: true };
    case "no-import": return { icon: "warn", tone: "warn", textKey: "frClaudeNoImport", connect: true };
    case "unreadable": return { icon: "warn", tone: "warn", textKey: "frClaudeUnreadable", connect: false };
    default: return null;
  }
}

/** Шлях для shell: прості символи — як є, інакше в одинарних лапках (`'` → `'\''`). */
export const shq = (s) => (/^[A-Za-z0-9_@%+=:,./~-]+$/.test(s) ? s : `'${String(s).replace(/'/g, "'\\''")}'`);

/** «Запуск агента»: `cd <тека простору> && claude` із шляху AGENTS.md; `""` — шляху нема. */
export function runCommand(agentsPath) {
  if (typeof agentsPath !== "string" || !agentsPath) return "";
  const i = agentsPath.lastIndexOf("/");
  const dir = i > 0 ? agentsPath.slice(0, i) : "/";
  return `cd ${shq(dir)} && claude`;
}

/** Рядок пароля на картці модуля: увімкнений, наявний постачальник ролі `publish` з налаштуванням `password` типу `secret`.
    `{state: "set"|"unset"|"unknown"}` або `null`. */
export function pwLine(e) {
  if (!e || e.enabled !== true || e.status === "missing" || !Array.isArray(e.roles) || !e.roles.includes("publish")) return null;
  const f = (Array.isArray(e.settings) ? e.settings : []).find((s) => s?.key === "password" && s.type === "secret");
  if (!f) return null;
  return { state: f.set === true ? "set" : f.set === false ? "unset" : "unknown" };
}

/** Пункт «Пароль превʼю» меню публікації: поле простору `publish_password` (`true|false|null`); поля нема — пункту нема. */
export function pwItem(space) {
  if (!space || !Object.prototype.hasOwnProperty.call(space, "publish_password")) return null;
  const v = space.publish_password;
  return { state: v === true ? "set" : v === false ? "unset" : "unknown" };
}

/** Стан пароля → ключ словника. */
export const PW_STATE_KEY = { set: "frPwSet", unset: "frPwUnset", unknown: "frPwUnknown" };
