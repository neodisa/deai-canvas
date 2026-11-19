/**
 * Каркас «Налаштувань» (етап Е): розділи, памʼять останнього й елементи лівої навігації. Чисті функції — ні DOM, ні `t()`.
 */
import { cardView, isOwn } from "./connections-model.js";

export const SECTIONS = ["space", "mods", "agents", "app", "upd", "keys"];
export const SEC_KEY = "deai.settingsSec";

/** Збережене значення → розділ; невідоме (чи не рядок) — `mods`. */
export const readSec = (stored) => (typeof stored === "string" && SECTIONS.includes(stored) ? stored : "mods");

const ITEMS = [
  { group: "space", id: "space", icon: "palette", labelKey: "setSecSpace" },
  { group: "space", id: "mods", icon: "puzzle", labelKey: "setSecMods" },
  { group: "space", id: "agents", icon: "doc", labelKey: "setSecAgents" },
  { group: "app", id: "app", icon: "desktop", labelKey: "setSecApp" },
  { group: "app", id: "upd", icon: "refresh", labelKey: "setSecUpd" },
  { group: "app", id: "keys", icon: "keyboard", labelKey: "setSecKeys" },
];

/** Навігація: `[{group, id, icon, labelKey, badge?: {kind:'count', n} | {kind:'dot'}}]`. */
export function navItems({ trustWaiting = 0, agentsOutdated = false } = {}) {
  return ITEMS.map((x) => {
    if (x.id === "mods" && trustWaiting > 0) return { ...x, badge: { kind: "count", n: trustWaiting } };
    if (x.id === "agents" && agentsOutdated) return { ...x, badge: { kind: "dot" } };
    return { ...x };
  });
}

/** Скільки своїх модулів чекає довіри (картка «Чекає довіри» або змінений код). Не масив — 0. */
export function trustWaitingOf(list) {
  if (!Array.isArray(list)) return 0;
  return list.filter((e) => isOwn(e) && (cardView(e).badge === "untrusted" || e.trust === "changed")).length;
}
