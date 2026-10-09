import assert from "node:assert/strict";
import test from "node:test";

import { setLang } from "../app/i18n.js";
import {
  cardHTML, defaultSort, effectiveSort, homeGridHTML, homeHTML, profileLabel, pruneFilters, safeThumb,
  safeUrl, sortsFor, thumbBrokenHTML,
} from "../app/tasks-home.js";

/* Дані — форма `/api/tasks-overview`: `mine[i]` має `changed` (секунди),
   `profile`, `missing`, `published`; `team.rows[i]` — `updated` (ISO),
   `designer`, `mine`, `preview`. `now` фіксований — відносний час детермінований. */
const NOW = Date.parse("2026-10-09T12:00:00Z");
const HOUR = 3600;
const M = (o) => ({
  id: "x", jira: null, title: "x", profile: "united", opened: null, iterations: 0, pages: 0,
  iter: null, changed: null, published: null, missing: false, thumb: null,
  jiraStatus: null, jiraCat: null, comments: null, ...o,
});
const R = (o) => ({
  id: "r", title: "r", jira: null, jiraStatus: null, jiraCat: null, comments: 0, thumb: null,
  preview: null, updated: null, designer: null, iterations: null, pages: null, mine: false, ...o,
});

const A = M({ id: "edr", jira: "LIGA-7019", title: "LIGA-7019 · Очікування оновлення даних із ЄДР",
  profile: "liga360", iterations: 3, pages: 5, changed: NOW / 1000 - 3 * HOUR,
  thumb: "/api/task-thumb?task=edr&v=abc", jiraStatus: "В роботі", jiraCat: "indeterminate",
  comments: 4, published: "https://pub.example/edr", opened: "2026-10-09T09:00:00Z" });
const B = M({ id: "sanc", jira: "LIGA-7015", title: "LIGA-7015: Санкції", profile: "united",
  changed: NOW / 1000 - 40 * 24 * HOUR, jiraStatus: "Готово", jiraCat: "done" });
const G = M({ id: "ghost", jira: "LIGA-7021", title: "Привид", profile: "seo", missing: true,
  iterations: 1 });
const DATA = {
  current: "edr", mine: [A, B, G],
  team: { error: null, fetchedAt: NOW / 1000, rowsAt: NOW / 1000, rows: [
    R({ id: "edr", title: "Очікування ЄДР", jira: "LIGA-7019", designer: "Ольга", mine: true,
      updated: "2026-10-09T09:00:00Z", iterations: 3, pages: 5 }),
    R({ id: "other", title: "Чужа задача", jira: "LIGA-1", designer: "Олег", mine: false,
      preview: "https://prev.example/other", updated: "2026-10-08T09:00:00Z", jiraStatus: "Готово", jiraCat: "done" }),
  ] },
};
const UI = (o = {}) => ({
  tab: "mine", q: "", sort: "recent", status: "all", profiles: new Set(), designers: new Set(),
  now: NOW, ...o,
});
const cards = (html) => (html.match(/class="th-card[ "]/g) || []).length;

setLang("uk");

test("вкладки: «Мої · N» і «Команда · M», активна — aria-selected", () => {
  const h = homeHTML(UI(), DATA);
  assert.match(h, /Мої · 3/);
  assert.match(h, /Команда · 2/);
  assert.match(h, /aria-selected="true" data-th="tab" data-v="mine"/);
  assert.match(h, /aria-selected="false" data-th="tab" data-v="team"/);
});

test("лічильники статусів рахуються ПІСЛЯ запиту, «Показано X з Y» — по фільтру", () => {
  const h = homeGridHTML(UI({ q: "санк", status: "all" }), DATA);
  assert.match(h, /Усі · 1/);
  assert.match(h, /Завершені · 1/);
  assert.match(h, /Активні · 0/);
  assert.match(h, /Показано 1 з 3/);
  assert.equal(cards(h), 1);
});

test("статус «Активні» ховає виконані, «Завершені» — лише виконані", () => {
  assert.equal(cards(homeGridHTML(UI({ status: "active" }), DATA)), 2);
  assert.equal(cards(homeGridHTML(UI({ status: "done" }), DATA)), 1);
});

test("картка «Моїх»: ключ, назва без ключа, мета, бейджі, кадр, превʼю", () => {
  const h = cardHTML(A, UI(), "other");
  assert.match(h, /<span class="th-key">LIGA-7019<\/span>/);
  assert.match(h, /class="th-ttl">Очікування оновлення даних із ЄДР</, "ключ у назві не дублюється");
  assert.match(h, /liga360|LIGA360/);
  assert.match(h, /Іт\. 3 · 5 стор\. · 3 год тому/);
  assert.match(h, /th-bdg--ind">В роботі</);
  assert.match(h, /th-bdg--com"[^>]*>[\s\S]*?4<\/span>/);
  assert.match(h, /<img class="th-img" src="\/api\/task-thumb\?task=edr&amp;v=abc" alt="" loading="lazy"/);
  assert.match(h, /<a class="th-lnk" href="https:\/\/pub\.example\/edr" target="_blank" rel="noopener"/);
  assert.doesNotMatch(h, /відкрита зараз/);
});

test("картка без Jira-статусу й без коментарів не малює порожніх бейджів", () => {
  const h = cardHTML(M({ id: "boss-interface", title: "boss-interface", comments: 0 }), UI(), "x2");
  assert.doesNotMatch(h, /th-bdg/);
  assert.match(h, /<span class="th-key">boss-interface<\/span>/);
  assert.match(h, /без ітерацій/);
  const nul = cardHTML(M({ id: "a", comments: null }), UI(), "z");
  assert.doesNotMatch(nul, /th-bdg--com/, "null = «невідомо», а не нуль коментарів");
});

test("кадру нема → камера й «немає кадру»; заглушка зламаного кадру окремо", () => {
  const h = cardHTML(B, UI(), "z");
  assert.match(h, /th-none/);
  assert.match(h, /немає кадру/);
  assert.doesNotMatch(h, /<img/);
  assert.match(thumbBrokenHTML(), /class="th-none">кадр недоступний</);
});

test("поточна задача: клас th-card--cur і «відкрита зараз»", () => {
  const h = cardHTML(A, UI(), "edr");
  assert.match(h, /class="th-card th-card--cur"/);
  assert.match(h, /· відкрита зараз/);
});

test("задача без теки: бейдж «теки немає…», aria-disabled, картка все одно data-th=open", () => {
  const h = cardHTML(G, UI(), "edr");
  assert.match(h, /th-bdg--warn/);
  assert.match(h, /теки немає на цій машині/);
  assert.match(h, /aria-disabled="true"/);
  assert.match(h, /th-card--miss/);
  // відкривається ЯК усі — відмову й причину дає обробник, а не відсутність кнопки
  assert.match(h, /data-th="open" data-id="ghost"/);
  assert.doesNotMatch(cardHTML(A, UI(), "z"), /aria-disabled/);
});

test("«Команда»: дизайнер у мета, час від updated, «Відкрити в канвасі» лише для своїх", () => {
  const ui = UI({ tab: "team", sort: "changed" });
  const mine = cardHTML(DATA.team.rows[0], ui, "edr");
  assert.match(mine, /Ольга · Іт\. 3 · 5 стор\. · 3 год тому/);
  assert.match(mine, /<button class="th-lnk" data-th="open" data-id="edr">[\s\S]*Відкрити в канвасі/);
  assert.doesNotMatch(mine, /<a /);
  assert.doesNotMatch(mine, /відкрита зараз/, "позначка «зараз» — лише на «Моїх»");
  const other = cardHTML(DATA.team.rows[1], ui, "edr");
  assert.match(other, /<a class="th-lnk" href="https:\/\/prev\.example\/other"/);
  assert.doesNotMatch(other, /Відкрити в канвасі/);
  assert.match(other, /role="group"/, "чужа задача без теки не вдає кнопку");
  assert.doesNotMatch(other, /data-th="open"/);
});

test("сортування: «Команда» без recent, типове changed; збережене recent там читається як changed", () => {
  assert.deepEqual(sortsFor("mine"), ["recent", "changed", "jira", "title", "status"]);
  assert.deepEqual(sortsFor("team"), ["changed", "jira", "title", "status"]);
  assert.equal(defaultSort("mine"), "recent");
  assert.equal(defaultSort("team"), "changed");
  assert.equal(effectiveSort(UI({ tab: "team", sort: "recent" })), "changed");
  const team = homeHTML(UI({ tab: "team", sort: "recent" }), DATA);
  assert.doesNotMatch(team, /value="recent"/);
  assert.match(team, /value="changed" selected/);
  const mine = homeHTML(UI(), DATA);
  assert.match(mine, /value="recent" selected/);
});

test("порядок карток слідує за сортуванням", () => {
  const ids = (h) => [...h.matchAll(/data-id="([^"]+)"/g)].map((m) => m[1]).filter((v, i, a) => a.indexOf(v) === i);
  assert.deepEqual(ids(homeGridHTML(UI({ sort: "jira" }), DATA)), ["ghost", "edr", "sanc"]);
  assert.deepEqual(ids(homeGridHTML(UI({ sort: "title" }), DATA)), ["edr", "ghost", "sanc"]);
});

test("чіпи напрямків на «Моїх» (мітки зі словника) і дизайнерів на «Команді»", () => {
  const mine = homeGridHTML(UI(), DATA);
  assert.match(mine, /data-th="profile" data-v="united"[^>]*>United</);
  assert.match(mine, /data-th="profile" data-v="liga360"[^>]*>LIGA360</);
  assert.match(mine, /data-th="profile" data-v="seo"[^>]*>SEO</);
  assert.doesNotMatch(mine, /data-th="designer"/);
  const team = homeGridHTML(UI({ tab: "team", sort: "changed" }), DATA);
  assert.match(team, /data-th="designer" data-v="Ольга"/);
  assert.match(team, /data-th="designer" data-v="Олег"/);
  assert.doesNotMatch(team, /data-th="profile"/);
  assert.equal(profileLabel("mystery"), "mystery", "невідомий напрямок лишається як є");
});

test("фільтр за напрямком і за дизайнером", () => {
  assert.equal(cards(homeGridHTML(UI({ profiles: new Set(["seo"]) }), DATA)), 1);
  assert.equal(cards(homeGridHTML(UI({ tab: "team", sort: "changed", designers: new Set(["Олег"]) }), DATA)), 1);
});

test("збій команди без рядків: банер із причиною й «Спробувати ще», сітки нема, вкладка «—»", () => {
  const d = { ...DATA, team: { rows: [], error: "VPN не відповів", fetchedAt: 1, rowsAt: null } };
  const ui = UI({ tab: "team", sort: "changed" });
  const h = homeHTML(ui, d);
  assert.match(h, /Команда · —/);
  assert.match(h, /class="th-banner"/);
  assert.match(h, /VPN не відповів/);
  assert.match(h, /data-th="retry"/);
  assert.match(h, /Спробувати ще/);
  assert.doesNotMatch(h, /th-grid/);
  assert.doesNotMatch(h, /дані на/);
  // «Мої» при тому ж збої живі
  assert.equal(cards(homeGridHTML(UI(), d)), 3);
  assert.doesNotMatch(homeGridHTML(UI(), d), /th-banner/);
});

test("збій команди з рядками (застарілі): банер, рядки лишаються, «дані на ГГ:ХХ» з rowsAt", () => {
  const rowsAt = Date.parse("2026-10-09T08:15:00Z") / 1000;
  const d = { ...DATA, team: { ...DATA.team, error: "таймаут", rowsAt } };
  const h = homeHTML(UI({ tab: "team", sort: "changed" }), d);
  assert.match(h, /Команда · 2/);
  assert.match(h, /таймаут/);
  assert.match(h, /class="th-stale">дані на \d{2}:\d{2}</);
  assert.equal(cards(h), 2);
  assert.match(h, /data-th="retry"/);
});

test("порожня видача: «Нічого не знайдено» + «Скинути фільтри»", () => {
  const h = homeGridHTML(UI({ q: "zzzнемає" }), DATA);
  assert.match(h, /Нічого не знайдено/);
  assert.match(h, /data-th="reset"[^>]*>Скинути фільтри</);
  assert.equal(cards(h), 0);
  assert.match(h, /Показано 0 з 3/);
});

test("підсвітка збігів екранована: теги з назви лишаються текстом, <mark> — наш", () => {
  const evil = M({ id: "e", jira: "LIGA-5", title: "LIGA-5 · <img src=x onerror=alert(1)> Тест" });
  const h = cardHTML(evil, UI({ q: "img тест" }), "z");
  assert.doesNotMatch(h, /<img src=x/, "теги з назви стали розміткою");
  assert.match(h, /&lt;<mark>img<\/mark> src=x/);
  assert.match(h, /<mark>Тест<\/mark>/);
  const attr = cardHTML(M({ id: 'q"><b>', title: "t" }), UI(), "z");
  assert.doesNotMatch(attr, /<b>/);
});

test("поле пошуку: значення екроване, плейсхолдер залежить від вкладки", () => {
  const h = homeHTML(UI({ q: '"><script>' }), DATA);
  assert.doesNotMatch(h, /<script>/);
  assert.match(h, /id="th-q"[^>]*placeholder="Номер, назва, статус…"/);
  assert.match(homeHTML(UI({ tab: "team", sort: "changed" }), DATA), /placeholder="Номер, назва, дизайнер…"/);
});

test("href лише з http(s): javascript:/data: не стають посиланнями", () => {
  assert.equal(safeUrl("https://a.example/x"), "https://a.example/x");
  assert.equal(safeUrl("javascript:alert(1)"), null);
  assert.equal(safeUrl("data:text/html,x"), null);
  assert.equal(safeUrl(null), null);
  const h = cardHTML(M({ id: "p", published: "javascript:alert(1)" }), UI(), "z");
  assert.doesNotMatch(h, /javascript:/);
  assert.doesNotMatch(h, /<a /);
});

test("до відповіді: вкладки й пошук є, у нижній частині «вантажу»; після збою — банер", () => {
  const h = homeHTML(UI(), { loading: true });
  assert.match(h, /id="th-q"/);
  assert.match(h, /Мої · —/);
  assert.match(h, /Завантажую задачі/);
  const f = homeHTML(UI(), { failed: "сервер мовчить" });
  assert.match(f, /Не вдалося завантажити задачі: сервер мовчить/);
  assert.match(f, /data-th="retry"/);
  assert.match(homeHTML(UI(), null), /Завантажую задачі/);
});

test("нижня частина (для перемальовки під час набору) не містить поля пошуку", () => {
  const g = homeGridHTML(UI(), DATA);
  assert.doesNotMatch(g, /id="th-q"/);
  assert.doesNotMatch(g, /<h1/);
  assert.match(g, /th-chips/);
  assert.match(g, /id="th-grid"/);
});

test("кадр: лише свій /api/task-thumb або http(s); решта — заглушка «немає кадру», не <img>", () => {
  assert.equal(safeThumb("/api/task-thumb?task=a&v=1"), "/api/task-thumb?task=a&v=1");
  assert.equal(safeThumb("https://cdn.example/x.png"), "https://cdn.example/x.png");
  for (const bad of ["javascript:alert(1)", "data:image/svg+xml,<svg/>", "//evil.example/x.png",
    "/api/other", "/etc/passwd", "x.png", "", null, undefined, 5, " javascript:alert(1)"]) {
    assert.equal(safeThumb(bad), null, `пропущено: ${String(bad)}`);
  }
  const h = cardHTML(M({ id: "p", thumb: "javascript:alert(1)" }), UI(), "z");
  assert.doesNotMatch(h, /<img/);
  assert.doesNotMatch(h, /javascript:/);
  assert.match(h, /немає кадру/);
  assert.doesNotMatch(cardHTML(M({ id: "q", thumb: "//evil.example/x" }), UI(), "z"), /<img/);
});

test("pruneFilters: знайомі значення лишаються, зниклі напрямки/дизайнери йдуть (невидимий фільтр)", () => {
  const ui = UI({ profiles: new Set(["united", "gone"]), designers: new Set(["Ольга", "Звільнений"]) });
  assert.equal(pruneFilters(ui, DATA), true);
  assert.deepEqual([...ui.profiles], ["united"]);
  assert.deepEqual([...ui.designers], ["Ольга"]);
  assert.equal(pruneFilters(ui, DATA), false, "нічого міняти — не пише");
});

test("pruneFilters: збій команди без рядків не стирає фільтр дизайнера, порожні «мої» — фільтр напрямку", () => {
  const ui = UI({ profiles: new Set(["united"]), designers: new Set(["Ольга"]) });
  const down = { ...DATA, team: { rows: [], error: "VPN", rowsAt: null } };
  pruneFilters(ui, down);
  assert.deepEqual([...ui.designers], ["Ольга"]);
  assert.equal(pruneFilters(ui, { mine: [], team: { rows: [], error: null } }), false);
  assert.deepEqual([...ui.profiles], ["united"]);
  assert.equal(pruneFilters(ui, null), false);
});

test("повторний запит не вдався, дані вже є: рядки лишаються, зверху банер збою завантаження", () => {
  const d = { ...DATA, loadError: "сервер мовчить" };
  const h = homeHTML(UI(), d);
  assert.equal(cards(h), 3, "добрі дані стерто");
  assert.match(h, /Не вдалося завантажити задачі: сервер мовчить/);
  assert.match(h, /data-th="retry"/);
  assert.doesNotMatch(homeHTML(UI(), DATA), /Не вдалося/);
});

test("вкладена кнопка «Відкрити в канвасі» має data-id (щоб після перемальовки фокус вернувся на ту саму)", () => {
  assert.match(cardHTML(DATA.team.rows[0], UI({ tab: "team", sort: "changed" }), "z"),
    /<button class="th-lnk" data-th="open" data-id="edr">/);
});
