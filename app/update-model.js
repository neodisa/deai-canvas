/**
 * Чиста модель оновлення інструмента (0.23.0): пігулка в смузі, довідка до кодів відмов, крок опиту після рестарту, розбір
 * «Що нового». Ні DOM, ні fetch, ні `t()` — лише дані й ІМЕНА ключів словника (як `bar-model.js`); текст складає `update-view.js`.
 *
 * Контракт сервера (`app/updater.py`): `GET /api/update` → `{current, latest, available, checked_at, state, reason, blocked,
 * remote_host, boot, last_update, restart_failed}`. `state` і `checked_at` — `null` до першої перевірки: це «ще не перевіряли», а не
 * помилка (пігулки немає, ручна перевірка в ⌘K працює). `boot` — випадковий id ПРОЦЕСУ сервера: рестарт видно саме по ньому.
 */

/** Скільки чекаємо новий процес після `202` (рестарт ~0,5 с + запуск Python), мс. */
export const RESTART_DEADLINE_MS = 60000;
/** Крок опиту `GET /api/update` після `202`, мс. */
export const RESTART_POLL_MS = 1000;
/** Фоновий опит стану оновлення, мс. Сервер сам питає remote раз на 6 год; тут лише знімаємо його результат. */
export const UPDATE_POLL_MS = 30 * 60 * 1000;

/**
 * Пігулка в смузі: `null` або `{version, labelKey, restart}`. Лише коли оновлення Є (`available`) І остання перевірка вдала
 * (`state === "ok"`): `offline`/`error`/`disabled`/`no-git` і `null` (ще не перевіряли) мовчать — пігулка, що веде в діалог, у
 * якому «Оновити» однаково впаде, була б шумом. Виняток — `restart_failed`: оновлення вже на диску, а процес лишився старий;
 * людині треба перезапустити канвас, і без пігулки цього діалогу ніде не знайти (`available` тоді вже `false` — диск нової версії).
 */
export function pillModel(update) {
  const u = update && typeof update === "object" ? update : null;
  if (!u) return null;
  if (u.restart_failed === true) {
    return { version: typeof u.current === "string" ? u.current : "", labelKey: "upPillRestart", restart: true };
  }
  if (u.available !== true || u.state !== "ok" || typeof u.latest !== "string" || !u.latest) return null;
  return { version: u.latest, labelKey: "upPill", restart: false };
}

/** Версія, яку безпечно підставити в команду для копіювання: лише `X.Y.Z` (сервер уже перевірив тег, але команда — це вже виконуване). */
const SEMVER = /^\d+\.\d+\.\d+$/;

/** Усі коди, що їх віддають `apply`/`notes` і `blocked` статусу (`updater.py`); для кожного є ключ `upCode_<код>` у словнику. */
export const KNOWN_CODES = [
  "not-git", "dirty", "detached", "worktree", "busy", "isolated", "diverged", "tag-conflict", "tag-missing", "tag-mismatch",
  "fetch-rejected", "offline", "disabled", "bad-remote", "no-remote", "rolled-back", "rollback-failed", "merge-failed",
  "nothing-to-update", "error",
];

/** Причини, з яких `GET /api/update-notes` не дав опису (`updater.notes`). Невідома причина → `error`. */
export const NOTES_REASONS = [
  "busy", "offline", "disabled", "no-update", "no-git", "fetch-rejected", "tag-missing", "tag-conflict", "no-changelog", "error",
  "bad-remote", "no-remote",
];

/** Ключ словника для коду відмови. Невідомий код — `upCode_generic` (там сам код іде аргументом). */
export const codeKey = (code) => (KNOWN_CODES.includes(code) ? `upCode_${code.replace(/-/g, "_")}` : "upCode_generic");

/**
 * Довідка до коду: `{key, command?, code}`. `command` — ШАБЛОН без шляхів, який можна скопіювати: `git stash` (чисте дерево),
 * `git merge v<latest>` (розійшлась гілка). Решта кодів — лише порада текстом. Без валідної `latest` команда з версією не дається.
 */
export function blockedHelp(code, latest) {
  const c = typeof code === "string" ? code : "";
  const out = { key: codeKey(c), code: KNOWN_CODES.includes(c) ? c : String(c || "error").slice(0, 40) };
  if (c === "dirty") out.command = "git stash";
  else if (c === "diverged" && typeof latest === "string" && SEMVER.test(latest)) out.command = `git merge v${latest}`;
  return out;
}

/** Код із тіла відповіді `apply`: `{ok:false, code}`; частина відмов (403) лише `{error}` — це «error». Без тіла — `error`. */
export function codeOfBody(body) {
  if (body && typeof body.code === "string" && body.code) return body.code;
  return "error";
}

/** Причина без опису для рядка в діалозі: відомий клас, або `error`. */
export const notesReasonClass = (reason) => (NOTES_REASONS.includes(reason) ? reason : "error");

/**
 * Один крок опиту після `202`. `ctx = {prevBoot, target, startedAt, now}`; `o` — що вийшло з `GET /api/update`:
 * `{ok:false}` (мережа/не JSON — сервер ще лежить) або `{ok:true, boot, current, restart_failed}`.
 *   - `restart_failed` у ТОМУ Ж процесі → `manual` (сервер сам визнав, що `execv` не вдався);
 *   - новий процес (`boot` змінився) із цільовою версією → `done`; із іншою → `fail` (відкат);
 *   - старий процес (той самий `boot`) бачить нову версію на диску вже після merge — це НЕ рестарт, чекаємо далі;
 *   - дедлайн → `fail`.
 */
export function restartStep(ctx, o) {
  const resp = o && o.ok === true ? o : null;
  if (resp && resp.boot === ctx.prevBoot && resp.restart_failed === true) return "manual";
  if (resp && typeof resp.boot === "string" && resp.boot !== ctx.prevBoot) {
    return resp.current === ctx.target ? "done" : "fail";
  }
  if (ctx.now - ctx.startedAt > RESTART_DEADLINE_MS) return "fail";
  return "wait";
}

/**
 * Тіло розділу CHANGELOG (звичайний текст) → блоки `{kind: "h" | "li" | "p", text}`. Рядок `### X` — заголовок, `- X`/`* X` — пункт,
 * решта непорожнє — абзац. ⛔ `text` — СИРИЙ текст (він може містити `<`/`>`): у розмітку він потрапляє лише через `esc` у
 * `update-view.js`; тут нічого не екранується й нічого не розбирається як HTML.
 */
export function bodyToBlocks(body) {
  const out = [];
  for (const raw of String(body ?? "").split("\n")) {
    const line = raw.replace(/\s+$/, "");
    if (!line.trim()) continue;
    let m;
    if ((m = /^#{2,6}\s+(.*)$/.exec(line))) out.push({ kind: "h", text: m[1] });
    else if ((m = /^\s*[-*]\s+(.*)$/.exec(line))) out.push({ kind: "li", text: m[1] });
    else out.push({ kind: "p", text: line.trim() });
  }
  return out;
}

/** Розділи `[{version, date, body}]` з сервера → `[{version, date, blocks}]`; усе, що не рядок, відкидається. */
export function notesToBlocks(sections) {
  if (!Array.isArray(sections)) return [];
  return sections
    .filter((s) => s && typeof s === "object")
    .map((s) => ({
      version: String(s.version ?? ""),
      date: String(s.date ?? ""),
      blocks: bodyToBlocks(s.body),
    }));
}
