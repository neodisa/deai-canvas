/**
 * «Перший запуск» (0.33.0): розмітка блока промпта на привітанні, знайомства (карта · легенда · цикл), картки ⌘K
 * «Знайомство з канвасом» і рядків «Запуск агента» / «Claude Code» розділу AGENTS.md. Чисті рядки — ні DOM, ні мережі;
 * поводження — `app.js`. Дані (шляхи, команди) — лише через `esc`; `kbdText` пропускає `<kbd>` лише з НАШИХ рядків словника.
 */
import { esc } from "./esc.js";
import { ico } from "./icons.js";
import { t } from "./i18n.js";
import { claudeRow, runCommand } from "./setup-model.js";

/** Текст словника з `[[X]]` → екранований, з `<kbd>X</kbd>`. */
export const kbdText = (s) => esc(s).replace(/\[\[([^\]]+)\]\]/g, "<kbd>$1</kbd>");

/** Промпт привітання: абсолютний шлях `paths.setup` з `GET /api/setup`; не відповів — описова фраза. */
export function promptText(setup, origin) {
  const p = typeof setup?.paths?.setup === "string" && setup.paths.setup ? setup.paths.setup : t("frPromptNoPath");
  return t("frPrompt", p, origin);
}

/** Блок «Налаштувати через агента» (привітання). Кнопка — `data-th="frcopy"` (`app.js` копіює текст `#fr-prompt`). */
export function agentBlockHTML(setup, origin) {
  return `<div class="fr-agent"><div class="fr-agent-h"><b>${esc(t("frAgentTitle"))}</b><span>${esc(t("frAgentLead"))}</span></div>`
    + `<pre class="prompt" id="fr-prompt">${esc(promptText(setup, origin))}</pre>`
    + `<div class="fr-agent-f"><button type="button" class="ctl ctl--pri" data-th="frcopy">${ico("copy", 15)}${esc(t("frCopyPrompt"))}</button></div></div>`;
}

/* Карта робочого місця — схема з блоків (без картинок), позначки 1–7 відповідають пунктам легенди. Для читача екрана
   її нема (`aria-hidden`): той самий зміст несе легенда `<ol>`. */
const MAP = `<div class="fr-map" aria-hidden="true">`
  + `<div class="fr-m-tabs"><span class="fr-m-tab fr-m-tab--on"></span><span class="fr-m-tab"></span><span class="fr-m-tab"></span></div>`
  + `<div class="fr-m-bar"><span class="fr-m-chip" style="width:18%"></span><span class="fr-m-chip" style="width:16%;margin-left:8%"></span>`
  + `<span class="fr-m-chip" style="width:10%"></span><span class="fr-m-pub"></span></div>`
  + `<div class="fr-m-tree"><i style="width:80%"></i><i style="width:64%"></i><i style="width:72%"></i><i style="width:56%"></i></div>`
  + `<div class="fr-m-stage"><div class="fr-m-page"><i style="top:10%;width:46%;height:7%"></i><i style="top:24%;width:80%"></i>`
  + `<i style="top:34%;width:70%"></i><i style="top:50%;width:36%;height:12%;background:var(--g300)"></i></div>`
  + `<span class="fr-m-spot" style="left:46%;top:44%"></span><div class="fr-m-isl"><i></i><i></i><i></i></div></div>`
  + [["2%", "1%"], ["5%", "11%"], ["30%", "11%"], ["76%", "11%"], ["5%", "30%"], ["55%", "38%"], ["65%", "83%"]]
    .map(([l, tp], i) => `<span class="fr-n" style="left:${l};top:${tp}">${i + 1}</span>`).join("")
  + `</div>`;

const LEGEND = [["frL1t", "frL1"], ["frL2t", "frL2"], ["frL3t", "frL3"], ["frL4t", "frL4"], ["frL5t", "frL5"], ["frL6t", "frL6"], ["frL7t", "frL7"]];
const CYCLE = [["frWhoAgent", "frC1t", "frC1"], ["frWhoYou", "frC2t", "frC2"], ["frWhoYou", "frC3t", "frC3"],
  ["frWhoAgent", "frC4t", "frC4"], ["frWhoYou", "frC5t", "frC5"]];

/** Карта + легенда + «Цикл роботи». `level` — рівень заголовка циклу (під `h2` розділу — 3). */
export function tourHTML(level = 3) {
  const legend = LEGEND.map(([b, s]) => `<li><span><b>${esc(t(b))}</b> ${kbdText(t(s))}</span></li>`).join("");
  const cycle = CYCLE.map(([who, b, s]) => `<li><span class="who">${esc(t(who))}</span><b>${esc(t(b))}</b><span>${kbdText(t(s))}</span></li>`).join("");
  return `<div class="fr-tour">${MAP}<ol class="fr-legend">${legend}</ol></div>`
    + `<h${level} class="fr-h3">${esc(t("frCycle"))}</h${level}><ol class="fr-cycle">${cycle}</ol>`;
}

/** Розділ «Знайомство» на привітанні. Рядка демо тут нема: простору ще нема (спека, розділ 4). */
export function introHTML() {
  return `<section class="fr-intro" aria-labelledby="fr-intro-h"><h2 class="fr-h2" id="fr-intro-h">${esc(t("frIntro"))}</h2>${tourHTML(3)}</section>`;
}

/** Картка ⌘K «Знайомство з канвасом» для `askForm`: «Закрити» — `data-a="cancel"` (оболонка закриває), «Відкрити демо» —
    `data-fr="demo"` (лише коли є поточний простір). */
export function introCardHTML({ demo = false } = {}) {
  const row = demo
    ? `<div class="fr-demo"><span class="fr-ic">${ico("task", 16)}</span><div class="set-row-l"><span class="set-row-t">${esc(t("frDemoTitle"))}</span>`
      + `<span class="set-row-s">${esc(t("frDemoText"))}</span></div>`
      + `<button type="button" class="ctl ctl--out" data-fr="demo">${esc(t("frDemoOpen"))}</button></div>`
    : "";
  return `<form class="fr-card" role="dialog" aria-modal="true" aria-labelledby="fr-card-t" novalidate>`
    + `<div class="fr-card-h"><h2 class="cv-ask-title" id="fr-card-t">${esc(t("frTour"))}</h2>`
    + `<button type="button" class="icob" data-a="cancel" data-autofocus aria-label="${esc(t("askClose"))}" title="${esc(t("askClose"))}">${ico("x", 16)}</button></div>`
    + `${tourHTML(3)}${row}<p data-form-error hidden></p></form>`;
}

/** Рядки «Запуск агента» і «Claude Code» над файлом у розділі AGENTS.md. `a` — відповідь `GET /api/agents-md`. */
export function agentRowsHTML(a, busy = false) {
  const cmd = runCommand(a?.path);
  const row = claudeRow(a?.claude, a?.hook);
  if (!cmd && !row) return "";
  const run = cmd
    ? `<div class="set-row"><span class="fr-ic">${ico("code", 16)}</span><div class="set-row-l"><span class="set-row-t">${esc(t("frRunTitle"))}</span>`
      + `<span class="set-row-s">${esc(t("frRunText"))}</span><div class="fr-cmd"><code class="cn-code" id="fr-run-cmd">${esc(cmd)}</code></div></div>`
      + `<div class="set-row-a"><button type="button" class="ctl ctl--out" data-th="ag" data-v="runcopy">${ico("copy")}${esc(t("frCopy"))}</button></div></div>`
    : "";
  // кнопка → [data-v, ключ підпису]: «Підключити» і «Оновити» — та сама дія (`{claude: true}`), «Відключити» знімає лише хук
  const BTN = { connect: ["claude", "frClaudeConnect"], update: ["claude", "frClaudeUpdate"], disconnect: ["unhook", "frClaudeDisconnect"] };
  const btn = row?.button ? BTN[row.button] : null;
  const will = row?.items.length
    ? `<ul class="fr-will">${row.items.map((i) => `<li><code>${esc(i.code)}</code> — ${esc(t(i.textKey))}</li>`).join("")}</ul>`
    : "";
  const cl = row
    ? `<div class="set-row" data-claude="${esc(a.claude.state)}"${a.hook?.state ? ` data-hook="${esc(a.hook.state)}"` : ""}>`
      + `<span class="fr-ic fr-ic--${row.tone}">${ico(row.icon, 16)}</span>`
      + `<div class="set-row-l"><span class="set-row-t">${esc(t("frClaudeTitle"))}</span>`
      + (row.textKey ? `<span class="set-row-s">${esc(t(row.textKey))}</span>` : "") + will + `</div>`
      + (btn ? `<div class="set-row-a"><button type="button" class="ctl ctl--out" data-th="ag" data-v="${btn[0]}"${busy ? " disabled" : ""}>${esc(t(btn[1]))}</button></div>` : "")
      + `</div>`
    : "";
  return `<div class="set-rows fr-run">${run}${cl}</div>`;
}
