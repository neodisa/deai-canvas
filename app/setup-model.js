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

const WILL_MD = { code: "CLAUDE.md", textKey: "frClaudeWillMd" };
const WILL_HOOK = { code: ".claude/settings.local.json", textKey: "frClaudeWillHook" };
const HOOK_STATES = ["ok", "missing", "stale", "unreadable", "elsewhere"];

/** Рядок «Claude Code» розділу AGENTS.md за `claude` і `hook` з `GET /api/agents-md`; `null` — стану CLAUDE.md нема.
    `{icon, tone, textKey | null, items: [{code, textKey}], button: null | "connect" | "update" | "disconnect"}`.
    `items` — список «що буде записано» (він і є згода людини; тоді пояснювального тексту нема). Старий сервер без `hook`
    (чи невідомий стан) — як у 0.33.0: лише CLAUDE.md. CLAUDE.md не читається — без кнопки, хук неважливий. */
export function claudeRow(claude, hook) {
  const cs = claude?.state;
  if (!["ok", "missing", "no-import", "unreadable"].includes(cs)) return null;
  const row = (icon, textKey, items = [], button = null) => ({ icon, tone: icon === "check" ? "ok" : "warn", textKey, items, button });
  if (cs === "unreadable") return row("warn", "frClaudeUnreadable");
  const hs = HOOK_STATES.includes(hook?.state) ? hook.state : null;
  if (hs === null) {
    if (cs === "ok") return row("check", "frClaudeOk");
    return row("warn", cs === "missing" ? "frClaudeMissing" : "frClaudeNoImport", [], "connect");
  }
  const hookItems = hs === "missing" || hs === "stale" ? [WILL_HOOK] : [];
  if (cs !== "ok") return row("warn", null, [WILL_MD, ...hookItems], "connect");
  switch (hs) {
    case "ok": return row("check", "frClaudeHookOk", [], "disconnect");
    case "missing": return row("warn", null, hookItems, "connect");
    case "stale": return row("warn", "frClaudeHookStale", [], "update");
    case "elsewhere": return row("warn", "frClaudeHookElsewhere");
    default: return row("warn", "frClaudeHookUnreadable");
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
