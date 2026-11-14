/**
 * Вкладки відкритих задач (етап А редизайну оболонки, 0.25.0). Чисті функції: жодного DOM і жодного
 * `localStorage` — читає/пише `app.js` під ключем `TABS_KEY`, тут лише формат і правила.
 *
 * Чому стан клієнтський, а не серверний: поточна задача на сервері одна (`POST /api/task-switch`), а
 * набір відкритих вкладок — звичка людини в цьому вікні; інше вікно канваса може мати свій набір.
 * Ключ вкладки — `id` задачі, бо сервер перемикає задачу саме за `id`.
 */
import { SPACE_COLORS } from "./spaces-model.js";

export const TABS_KEY = "dc-tabs";
export const TABS_MAX = 12;
const STR_MAX = 200;
const CLAUDE_STATES = ["working", "waiting", "blocked", "done"];

const str = (v) => (typeof v === "string" ? v.slice(0, STR_MAX) : "");
const strOrNull = (v) => (typeof v === "string" && v ? v.slice(0, STR_MAX) : null);

function clean(x) {
  if (!x || typeof x !== "object") return null;
  const id = str(x.id);
  if (!id) return null;
  return {
    id,
    title: str(x.title),
    space: strOrNull(x.space),
    /* Колір іде в `style` (`tabs-view.js`): лише значення з білого списку, інакше `null`. */
    color: SPACE_COLORS.includes(x.color) ? x.color : null,
    jira: strOrNull(x.jira),
  };
}

/** Рядок зі сховища → масив вкладок. Будь-яке сміття — порожньо, без винятку. */
export function readTabs(raw) {
  let data;
  try { data = JSON.parse(raw); } catch (e) { return []; }
  if (!data || data.v !== 1 || !Array.isArray(data.tabs)) return [];
  const seen = new Set();
  const out = [];
  for (const x of data.tabs) {
    const t = clean(x);
    if (!t || seen.has(t.id)) continue;
    seen.add(t.id);
    out.push(t);
  }
  return out.slice(-TABS_MAX);
}

export const writeTabs = (tabs) => JSON.stringify({ v: 1, tabs });

/** Відкрити (чи оновити) вкладку. Нова — в кінець; понад ліміт випадає найстаріша, крім щойно відкритої. */
export function upsertTab(tabs, rec) {
  const t = clean(rec);
  if (!t) return tabs;
  const i = tabs.findIndex((x) => x.id === t.id);
  if (i >= 0) return tabs.map((x, j) => (j === i ? t : x));
  const out = [...tabs, t];
  while (out.length > TABS_MAX) out.splice(out.findIndex((x) => x.id !== t.id), 1);
  return out;
}

/** Закрити вкладку. `next`: `null` — активна не змінилась; id — куди перейти; `"home"` — вкладок не лишилось. */
export function closeTab(tabs, id, activeId) {
  const i = tabs.findIndex((x) => x.id === id);
  if (i < 0) return { tabs, next: null };
  const rest = tabs.filter((x) => x.id !== id);
  if (id !== activeId) return { tabs: rest, next: null };
  const right = tabs[i + 1];
  const left = tabs[i - 1];
  return { tabs: rest, next: right ? right.id : left ? left.id : "home" };
}

/** Прибрати вкладки ПОТОЧНОГО простору, яких більше нема в його списку задач (поправка 4). */
export function pruneTabs(tabs, spaceId, liveIds) {
  const live = new Set(liveIds);
  const sp = spaceId ?? null;
  return tabs.filter((x) => x.space !== sp || live.has(x.id));
}

/** Модель рядка вкладок для `tabs-view.js`. `claude` — `{ключ: {state}}` з `/api/claude-statuses` або `null`. */
export function tabsModel({ tabs, activeId, homeOpen = false, homePage = "tasks", claude = null, update = null, news = null }) {
  const stateOf = (t) => {
    const v = claude && (claude[t.id] || (t.jira && claude[t.jira]));
    return v && CLAUDE_STATES.includes(v.state) ? v.state : null;
  };
  return {
    logoOn: !!homeOpen && homePage === "tasks",
    gearOn: !!homeOpen && homePage === "conn",
    update,
    items: tabs.map((t) => ({
      id: t.id, title: t.title, color: t.color,
      active: !homeOpen && t.id === activeId,
      claude: stateOf(t),
      news: news && Number(news[t.id]) > 0 ? Number(news[t.id]) : 0,
    })),
  };
}
