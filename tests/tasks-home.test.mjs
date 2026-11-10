import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { DICT, setLang, t } from "../app/i18n.js";
import { filterTasks } from "../app/tasks-model.js";
import {
  cardHTML, defaultSort, effectiveSort, effectiveTab, homeGridHTML, homeHTML, pruneFilters, safeThumb,
  safeUrl, sortsFor, thumbBrokenHTML,
} from "../app/tasks-home.js";

/* Дані — форма `/api/tasks-overview`: `mine[i]` має `changed` (секунди),
   `profile`, `tags`, `missing`, `published`; `team.rows[i]` — `updated` (ISO),
   `designer`, `mine`, `preview`. `now` фіксований — відносний час детермінований. */
const NOW = Date.parse("2026-10-09T12:00:00Z");
const HOUR = 3600;
/* Похідна мітка ЛІГИ — як її віддає сервер, коли в задачі нема власних `tags` (`task_tags`, `tracks._LEGACY_LABELS` через `label_tag`). */
const DERIVED = { united: "United", liga360: "LIGA360", seo: "SEO" };
const tagsOf = (profile) => (profile == null ? [] : [DERIVED[profile] ?? profile]);
const M = (o) => {
  const x = {
    id: "x", jira: null, title: "x", profile: "united", opened: null, iterations: 0, pages: 0,
    iter: null, changed: null, published: null, missing: false, thumb: null,
    jiraStatus: null, jiraCat: null, comments: null, ...o,
  };
  return "tags" in o ? x : { ...x, tags: tagsOf(x.profile) };
};
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
  tab: "mine", q: "", sort: "recent", status: "all", tags: new Set(), designers: new Set(),
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

test("чіпи міток на «Моїх» (з x.tags) і дизайнерів на «Команді»", () => {
  const mine = homeGridHTML(UI(), DATA);
  assert.match(mine, /data-th="tag" data-v="united"[^>]*>United</);
  assert.match(mine, /data-th="tag" data-v="liga360"[^>]*>LIGA360</);
  assert.match(mine, /data-th="tag" data-v="seo"[^>]*>SEO</);
  assert.doesNotMatch(mine, /data-th="designer"|data-th="profile"/);
  const team = homeGridHTML(UI({ tab: "team", sort: "changed" }), DATA);
  assert.match(team, /data-th="designer" data-v="Ольга"/);
  assert.match(team, /data-th="designer" data-v="Олег"/);
  assert.doesNotMatch(team, /data-th="tag"|data-th="profile"/);
});

/** Чипи міток у порядку розмітки: `[ключ, aria-pressed, підпис]`. */
const tagChips = (h) => [...h.matchAll(/data-th="tag" data-v="([^"]*)" aria-pressed="(\w+)">([^<]*)</g)].map((m) => [m[1], m[2], m[3]]);

test("чіпи міток: ключ — без регістру, підпис — перший побачений запис, порядок — кількість задач ↓, далі абетка", () => {
  const data = { ...DATA, mine: [
    M({ id: "a", tags: ["Zeta", "alpha"] }), M({ id: "b", tags: ["zeta"] }), M({ id: "c", tags: ["ZETA", "Beta"] }),
    M({ id: "d", tags: ["gamma"] }), M({ id: "e", tags: [] }), M({ id: "f", tags: ["beta"] }),
  ] };
  assert.deepEqual(tagChips(homeGridHTML(UI(), data)), [
    ["zeta", "false", "Zeta"],      // 3 задачі; підпис — перший запис, а не «zeta»/«ZETA»
    ["beta", "false", "Beta"],      // 2
    ["alpha", "false", "alpha"],    // по 1: абетка (alpha < gamma)
    ["gamma", "false", "gamma"],
  ]);
  /* Одна задача з двома записами однієї мітки лічиться раз, а не двічі: інакше «x» (2 записи в 1 задачі) обійшла б «y» (у 2 задачах). */
  const dup = { ...DATA, mine: [M({ id: "a", tags: ["x", "X"] }), M({ id: "b", tags: ["y"] }), M({ id: "c", tags: ["y"] })] };
  assert.deepEqual(tagChips(homeGridHTML(UI(), dup)).map((c) => c[0]), ["y", "x"]);
});

test("чіпи міток: aria-pressed за ui.tags; порожні й пробільні мітки чипа не дають; мітка екранується", () => {
  const evil = '<img src=x onerror=alert(1)>';
  const data = { ...DATA, mine: [M({ id: "a", tags: ["alpha", "", "   ", evil]}), M({ id: "b", tags: ["alpha"] })] };
  const h = homeGridHTML(UI({ tags: new Set(["alpha"]) }), data);
  assert.deepEqual(tagChips(h).map((c) => c.slice(0, 2)).filter((c) => c[0] === "alpha"), [["alpha", "true"]]);
  assert.match(h, /th-chip th-chip--on" data-th="tag" data-v="alpha"/, "вибраний чип підсвічений");
  assert.equal(tagChips(h).length, 2, "alpha й мітка зі шкідливим текстом; порожні — ні");
  assert.doesNotMatch(h, /<img src=x/);
  assert.match(h, /&lt;img src=x onerror=alert\(1\)&gt;/);
});

test("рядок картки «Моїх»: мітки через «, »; без міток — частини нема; «Команда» без змін", () => {
  const meta = (h) => /<div class="th-meta">([^]*?)<\/div>/.exec(h)[1];
  assert.equal(meta(cardHTML(M({ id: "a", tags: ["alpha", "Beta"], iterations: 2 }), UI(), "z")).split(" · ")[0], "alpha, Beta");
  assert.equal(meta(cardHTML(M({ id: "a", tags: [], iterations: 2 }), UI(), "z")).split(" · ")[0], t("thIter", 2),
    "без міток першою частиною стає наступна, а не порожній відступ");
  assert.doesNotMatch(meta(cardHTML(M({ id: "a", tags: [], iterations: 0 }), UI(), "z")), /^,|, ,|undefined|null/);
  assert.match(meta(cardHTML(M({ id: "a", tags: ["<b>x</b>"], iterations: 0 }), UI(), "z")), /^&lt;b&gt;x&lt;\/b&gt; · /, "мітка екранується");
  assert.match(meta(cardHTML(R({ designer: "Ольга", iterations: 1 }), UI({ tab: "team" }), "z")), /^Ольга · /);
});

test("кнопка «Мітки»: на «Моїх» є (data-th=tags, data-id, підпис зі словника), на «Команді» нема", () => {
  const mine = cardHTML(M({ id: "a<b", jira: "LIGA-1", tags: ["x"] }), UI(), "z");
  assert.match(mine, /<button class="th-lnk" data-th="tags" data-id="a&lt;b"[^>]*>[^]*?Мітки<\/button>/);
  assert.match(mine, /aria-label="Мітки задачі LIGA-1"/, "кнопку на кожній картці відрізняє підпис із ключем задачі");
  const team = cardHTML(R({ id: "r", mine: true }), UI({ tab: "team" }), "z");
  assert.doesNotMatch(team, /data-th="tags"/);
  assert.doesNotMatch(cardHTML(R({ id: "r" }), UI({ tab: "team" }), "z"), /data-th="tags"/);
  const gone = cardHTML(M({ id: "g", missing: true }), UI(), "z");
  assert.match(gone, /data-th="tags"/, "задача без теки теж має мітки (вони в реєстрі, не в теці)");
});

/* ── диференційний: мітки, похідні від профілів, дають те саме, що давав профільний вигляд 0.10.0 ───── */

const SNAP = JSON.parse(readFileSync(new URL("./fixtures/task-tags/before-4b3.json", import.meta.url), "utf8"));

test("диференційний: підписи чипів і перша частина картки збігаються зі знімком 0.10.0 (порядок — свідома відмінність)", () => {
  const profiles = SNAP.chips.fixture_profiles;
  const mine = profiles.map((p, i) => M({ id: `t${i + 1}`, profile: p }));
  const ui = UI({ tags: new Set(SNAP.chips.selected) });
  const now = tagChips(homeGridHTML(ui, { ...DATA, mine }));
  assert.deepEqual(new Set(now.map((c) => c[2])), new Set(SNAP.chips.chips.map((c) => c.label)), "ті самі підписи");
  for (const old of SNAP.chips.chips) {
    assert.deepEqual(now.find((c) => c[0] === old.v)?.slice(1), [old.pressed, old.label], `чип ${old.v}`);
  }
  for (const [key, first] of Object.entries(SNAP.card_meta)) {
    const p = key === "null" ? null : key;
    const h = cardHTML(M({ id: "c", profile: p, iterations: 0 }), UI(), "z");
    assert.equal(/<div class="th-meta">([^]*?)<\/div>/.exec(h)[1].split(" · ")[0], first, `перша частина картки, профіль ${key}`);
  }
  /* Фільтр за «united»: ті самі задачі, ОКРІМ задачі без профілю (свідома відмінність: без міток тепер ховається). */
  const sel = [...SNAP.chips.selected];
  const noProfile = mine.filter((x) => x.profile === null).map((x) => x.id);
  assert.deepEqual(noProfile, ["t6"]);
  assert.deepEqual(filterTasks(mine, { tags: new Set(sel) }).map((x) => x.id), SNAP.chips.kept_ids.filter((id) => !noProfile.includes(id)));
});

test("фільтр за міткою і за дизайнером", () => {
  assert.equal(cards(homeGridHTML(UI({ tags: new Set(["seo"]) }), DATA)), 1);
  assert.equal(cards(homeGridHTML(UI({ tags: new Set(["seo", "united"]) }), DATA)), 2, "АБО");
  assert.equal(cards(homeGridHTML(UI({ tab: "team", sort: "changed", designers: new Set(["Олег"]) }), DATA)), 1);
  assert.equal(cards(homeGridHTML(UI({ tab: "team", sort: "changed", tags: new Set(["seo"]) }), DATA)), 2,
    "вибрана мітка не чіпає «Команду»: у її рядків міток нема");
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

/* 4c-2: банер «Трекер недоступний» — лише на «Моїх» (статуси трекера живуть у їхніх картках), `tracker` = `null` | `{error, okAt}`. */
const TRK_AT = Date.parse("2026-10-09T08:15:00Z") / 1000;

test("збій трекера: на «Моїх» банер «Трекер недоступний: …» + «дані на ГГ:ХХ» з okAt, картки лишаються", () => {
  const d = { ...DATA, tracker: { error: "Jira недосяжна (OSError)", okAt: TRK_AT } };
  const h = homeGridHTML(UI(), d);
  assert.match(h, /class="th-banner"/);
  assert.match(h, /Трекер недоступний: Jira недосяжна \(OSError\)/);
  assert.match(h, /class="th-stale">дані на \d{2}:\d{2}</);
  assert.match(h, /data-th="retry"/);
  assert.equal(cards(h), 3, "збій трекера не ховає картки");
});

test("збій трекера без okAt (успіху ще не було): банер без часу", () => {
  const h = homeGridHTML(UI(), { ...DATA, tracker: { error: "Jira не налаштовано", okAt: null } });
  assert.match(h, /Трекер недоступний: Jira не налаштовано/);
  assert.doesNotMatch(h, /th-stale/);
  assert.doesNotMatch(h, /дані на/);
});

test("трекер: null чи без error — банера нема; поле tracker старої відповіді не обовʼязкове", () => {
  assert.doesNotMatch(homeGridHTML(UI(), { ...DATA, tracker: null }), /th-banner/);
  assert.doesNotMatch(homeGridHTML(UI(), { ...DATA, tracker: { error: null, okAt: TRK_AT } }), /th-banner/);
  assert.doesNotMatch(homeGridHTML(UI(), DATA), /th-banner/);
});

test("збій трекера на вкладці «Команда» банера не дає, а збій команди на «Моїх» — не змішується", () => {
  const d = { ...DATA, tracker: { error: "Jira лежить", okAt: TRK_AT } };
  const team = homeGridHTML(UI({ tab: "team", sort: "changed" }), d);
  assert.doesNotMatch(team, /Трекер недоступний/);
  assert.doesNotMatch(team, /th-banner/);
  assert.equal(cards(team), 2);
  const both = { ...d, team: { ...DATA.team, error: "таймаут", rowsAt: TRK_AT } };
  const mine = homeGridHTML(UI(), both);
  assert.match(homeGridHTML(UI({ tab: "team", sort: "changed" }), both), /Дашборд команди недоступний/);
  assert.match(mine, /Трекер недоступний/);
  assert.doesNotMatch(mine, /Дашборд команди недоступний/);
});

test("текст помилки трекера екранований: <b> лишається текстом", () => {
  const h = homeGridHTML(UI(), { ...DATA, tracker: { error: "<b>x</b><img src=x onerror=alert(1)>", okAt: null } });
  assert.doesNotMatch(h, /<b>x<\/b>/);
  assert.doesNotMatch(h, /<img src=x/);
  assert.match(h, /&lt;b&gt;x&lt;\/b&gt;/);
});

test("збій трекера: текст є в обох мовах словника", () => {
  assert.match(DICT.uk.thTrackerErr("x"), /^Трекер недоступний: x/);
  assert.match(DICT.en.thTrackerErr("x"), /^Issue tracker unavailable: x/);
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

test("pruneFilters: знайомі значення лишаються, зниклі мітки/дизайнери йдуть (невидимий фільтр)", () => {
  const ui = UI({ tags: new Set(["united", "gone"]), designers: new Set(["Ольга", "Звільнений"]) });
  assert.equal(pruneFilters(ui, DATA), true);
  assert.deepEqual([...ui.tags], ["united"]);
  assert.deepEqual([...ui.designers], ["Ольга"]);
  assert.equal(pruneFilters(ui, DATA), false, "нічого міняти — не пише");
});

test("pruneFilters: ключі міток — за tagKey (регістр), а мітка, прибрана з усіх задач, знімає й фільтр", () => {
  const ui = UI({ tags: new Set(["alpha", "beta"]) });
  assert.equal(pruneFilters(ui, { ...DATA, mine: [M({ id: "a", tags: ["Alpha"] })] }), true);
  assert.deepEqual([...ui.tags], ["alpha"], "«Alpha» у даних = ключ alpha; beta зникла");
  assert.equal(pruneFilters(ui, { ...DATA, mine: [M({ id: "a", tags: [] })] }), true, "останню мітку прибрано — фільтр не лишається невидимим");
  assert.deepEqual([...ui.tags], []);
});

test("pruneFilters: збій команди без рядків не стирає фільтр дизайнера, порожні «мої» — фільтр міток", () => {
  const ui = UI({ tags: new Set(["united"]), designers: new Set(["Ольга"]) });
  const down = { ...DATA, team: { rows: [], error: "VPN", rowsAt: null } };
  pruneFilters(ui, down);
  assert.deepEqual([...ui.designers], ["Ольга"]);
  assert.equal(pruneFilters(ui, { mine: [], team: { rows: [], error: null } }), false);
  assert.deepEqual([...ui.tags], ["united"]);
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

/* ── простори (Deai 1.0, етап 1) ──────────────────────────────────────────────
   `data.space` — те, що `/api/tasks-overview` віддає поруч з `mine`/`team`.
   Простір без дашборда команди (`capabilities.dashboard == null`, 4d-4c; було `integrations === false`): дашборда команди нема (`team: null`) — вкладки
   «Команда» немає, а збережена в UI вкладка `team` читається як `mine` (інакше
   екран малював би порожній список під вкладкою, якої нема). «Нова задача» —
   єдиний спосіб завести задачу не з Jira-реєстру, тож кнопка стоїть у голові
   екрана саме там, де інтеграцій нема. */
const NO_DASH = { dashboard: null };
const OFF = { name: "P", capabilities: NO_DASH };
const WITH_DASH = { dashboard: "supabase-dashboard" };
const D_OFF = (o = {}) => ({ current: null, mine: [], team: null, space: OFF, ...o });

test("простір без дашборда: заголовок «Задачі · P», вкладки «Команда» нема, є «Нова задача»", () => {
  const h = homeHTML(UI(), D_OFF());
  assert.match(h, /<h1 class="th-h">Задачі · P<\/h1>/);
  assert.doesNotMatch(h, /data-v="team"/, "вкладка команди без дашборда");
  assert.doesNotMatch(h, /Команда/);
  assert.match(h, /data-v="mine"/);
  assert.match(h, /<button[^>]*class="ctl ctl--pri"[^>]*data-th="newtask"|<button[^>]*data-th="newtask"[^>]*class="ctl ctl--pri"/);
  assert.match(h, /Нова задача/);
});

/* Вхід на екран «Підключення» (етап 3a) із голови «Задач». Той самий принцип, що в «Нова задача»: лише там, де
   інтеграцій нема, — голова простору ЛІГА лишається побайтно як була (один `<h1>`). Обидві кнопки — в обгортці
   `.th-head-acts`: вона один флекс-елемент голови, тож коли довга назва простору не лишає місця, `.th-head`
   (`flex-wrap:wrap`, див. `tests/spaces-css.test.mjs`) переносить під заголовок обидві кнопки разом, а не по одній. */
test("голова простору без дашборда: «Підключення» поряд із «Нова задача»; простір ЛІГА — без змін", () => {
  const off = homeHTML(UI(), D_OFF());
  assert.match(off, /<div class="th-head-acts"><button class="ctl ctl--out" data-th="conn">[\s\S]*?Підключення<\/button><button class="ctl ctl--pri" data-th="newtask">/);
  const liga = homeHTML(UI(), { ...DATA, space: { name: "Liga", capabilities: WITH_DASH } });
  assert.doesNotMatch(liga, /data-th="conn"/);
  /* Кнопка з іконкою `sliders`, а голова ЛІГА — як була: без обгортки й без `th-head`. */
  assert.match(/<button[^>]*data-th="conn">[\s\S]*?<\/button>/.exec(off)[0], /#i-sliders/);
  assert.doesNotMatch(liga, /th-head/);
  assert.match(liga, /<div class="th-in">\s*<h1 class="th-h">Задачі · Liga<\/h1>\s*<div class="th-tabs"/);
  /* Без `space` і без відомостей про роль `dashboard` — теж без кнопки: вимикач лише коли відповідь знає `capabilities`
     і роль у ній порожня (невідомість не краде в людини команду). */
  for (const space of [undefined, null, { name: "P" }, { name: "P", capabilities: {} }, { name: "P", capabilities: "x" },
    { name: "P", capabilities: { publish: null } }]) {
    assert.doesNotMatch(homeHTML(UI(), { ...DATA, space }), /data-th="conn"/, JSON.stringify(space));
  }
});

test("«Підключення» в голові — і поки дані вантажаться, рівно одна, поза порожнім станом", () => {
  const loading = homeHTML(UI(), { loading: true, space: OFF });
  assert.equal((loading.match(/data-th="conn"/g) || []).length, 1);
  const h = homeHTML(UI(), D_OFF());
  assert.equal((h.match(/data-th="conn"/g) || []).length, 1, "порожній стан простору кнопки підключень не дублює");
  assert.equal((homeHTML(UI(), D_OFF({ mine: [A, B], current: "edr" })).match(/data-th="conn"/g) || []).length, 1);
  /* Нижня частина (сітка) перемальовується окремо й голови не має. */
  assert.doesNotMatch(homeGridHTML(UI(), D_OFF()), /data-th="conn"/);
});

test("«Підключення» в голові — англійською «Connections»", () => {
  setLang("en");
  try {
    assert.match(homeHTML(UI(), D_OFF()), /data-th="conn">[\s\S]*?Connections<\/button>/);
  } finally { setLang("uk"); }
});

test("простір без дашборда і без задач: порожній стан із підказкою агентові й кнопкою", () => {
  const h = homeHTML(UI(), D_OFF());
  assert.match(h, /class="th-empty[ "]/);
  assert.match(h, /Тут ще нема задач/);
  assert.match(h, /простор[іу] P/i, "підказка агентові не називає простір");
  assert.equal((h.match(/data-th="newtask"/g) || []).length, 2, "кнопка в голові + кнопка в порожньому стані");
  const box = /<div class="th-empty th-empty--space">[\s\S]*?<\/div><\/div>/.exec(h)?.[0];
  assert.ok(box, "порожній стан простору — окремий вузол th-empty--space");
  assert.match(box, /<div class="th-empty-act"><button[^>]*data-th="newtask"/, "кнопка в обгортці th-empty-act");
  assert.doesNotMatch(h, /Нічого не знайдено/, "це не «порожня видача», а порожній простір");
  assert.doesNotMatch(h, /data-th="reset"/, "скидати нічого");
});

test("порожній стан простору — і в нижній частині, що перемальовується окремо", () => {
  const g = homeGridHTML(UI(), D_OFF());
  assert.match(g, /Тут ще нема задач/);
  assert.match(g, /id="th-grid"/);
});

test("простір без дашборда із задачами: картки, без порожнього стану; «Нова задача» лише в голові", () => {
  const h = homeHTML(UI(), D_OFF({ mine: [A, B], current: "edr" }));
  assert.equal(cards(h), 2);
  assert.doesNotMatch(h, /Тут ще нема задач/);
  assert.equal((h.match(/data-th="newtask"/g) || []).length, 1);
});

test("простір без дашборда: фільтр сховав усе — це «Нічого не знайдено», не «порожній простір»", () => {
  const h = homeHTML(UI({ q: "zzzнемає" }), D_OFF({ mine: [A, B] }));
  assert.match(h, /Нічого не знайдено/);
  assert.doesNotMatch(h, /Тут ще нема задач/);
});

test("збережена вкладка `team` при `team: null` малюється як `mine`", () => {
  const ui = UI({ tab: "team", sort: "changed" });
  const h = homeHTML(ui, D_OFF({ mine: [A, B] }));
  assert.match(h, /aria-selected="true" data-th="tab" data-v="mine"/);
  assert.equal(cards(h), 2, "картки «Моїх» мусять бути видні");
  assert.match(h, /placeholder="Номер, назва, статус…"/, "плейсхолдер вкладки «Мої»");
  assert.doesNotMatch(h, /Відкрити в канвасі/, "картка команди просочилась");
  assert.equal(effectiveTab(ui, D_OFF()), "mine");
  // і нижня частина, що перемальовується окремо, читає вкладку так само
  assert.equal(cards(homeGridHTML(ui, D_OFF({ mine: [A, B] }))), 2);
  // сортування вкладки «Мої» (є recent), а не збережене командне
  assert.match(h, /<option value="changed" selected>/, "changed існує і на «Моїх» — лишається");
  const recent = homeHTML(UI({ tab: "team", sort: "recent" }), D_OFF({ mine: [A, B] }));
  assert.match(recent, /<option value="recent" selected>/);
});

test("effectiveTab: `team` лишається, коли команда є; мої — завжди мої", () => {
  assert.equal(effectiveTab(UI({ tab: "team" }), DATA), "team");
  assert.equal(effectiveTab(UI({ tab: "mine" }), DATA), "mine");
  assert.equal(effectiveTab(UI({ tab: "mine" }), D_OFF()), "mine");
  // команда з помилкою — усе ще команда (`team` — обʼєкт)
  const err = { ...DATA, team: { rows: [], error: "VPN", fetchedAt: 1, rowsAt: null } };
  assert.equal(effectiveTab(UI({ tab: "team" }), err), "team");
});

test("до відповіді: вкладки на місці; відомий простір без дашборда ховає «Команду» одразу", () => {
  // без відомостей про простір — як було (вкладки є «поки вантажиться»)
  assert.match(homeHTML(UI(), { loading: true }), /data-v="team"/);
  assert.match(homeHTML(UI(), null), /data-v="team"/);
  // а простір відомий — вкладка не мигає на мить завантаження
  const h = homeHTML(UI(), { loading: true, space: OFF });
  assert.doesNotMatch(h, /data-v="team"/);
  assert.match(h, /Задачі · P/);
  assert.match(h, /Завантажую задачі/);
  assert.equal((h.match(/data-th="newtask"/g) || []).length, 1, "кнопка в голові є й до відповіді; порожнього стану ще нема");
});

test("з дашбордом: кнопки «Нова задача» нема, вкладки й заголовок як були", () => {
  const withInt = { name: "ЛІГА", capabilities: WITH_DASH };
  const h = homeHTML(UI(), { ...DATA, space: withInt });
  assert.doesNotMatch(h, /data-th="newtask"/);
  assert.match(h, /data-v="team"/);
  assert.match(h, /Мої · 3/);
  assert.match(h, /<h1 class="th-h">Задачі · ЛІГА<\/h1>/, "назва простору в заголовку — і з інтеграціями");
  // порожні «мої» в просторі З інтеграціями — звичайне «Нічого не знайдено», не екран агента
  const empty = homeHTML(UI(), { ...DATA, mine: [], space: withInt });
  assert.doesNotMatch(empty, /Тут ще нема задач/);
});

test("без `space` екран такий, як був: заголовок «Задачі», кнопки нема", () => {
  const h = homeHTML(UI(), DATA);
  assert.match(h, /<h1 class="th-h">Задачі<\/h1>/);
  assert.doesNotMatch(h, /data-th="newtask"/);
  assert.match(h, /data-v="team"/);
  const nulled = homeHTML(UI(), { ...DATA, space: null });
  assert.match(nulled, /<h1 class="th-h">Задачі<\/h1>/);
});

test("команда без ключа `team` (стара форма відповіді) — вкладки нема, як і при null", () => {
  const { team, ...noTeam } = DATA;
  const h = homeHTML(UI({ tab: "team" }), noTeam);
  assert.doesNotMatch(h, /data-v="team"/);
  assert.match(h, /aria-selected="true" data-th="tab" data-v="mine"/);
});

test("назва простору екранується в заголовку й у підказці агентові", () => {
  const evil = '<img src=x onerror=alert(1)>';
  const h = homeHTML(UI(), D_OFF({ space: { name: evil, capabilities: NO_DASH } }));
  assert.doesNotMatch(h, /<img src=x/);
  assert.match(h, /&lt;img src=x/);
});

test("pruneFilters при `team: null` не кидає і не чіпає дизайнерів", () => {
  const ui = UI({ designers: new Set(["Хтось"]), tags: new Set() });
  assert.doesNotThrow(() => pruneFilters(ui, D_OFF({ mine: [A] })));
  assert.ok(ui.designers.has("Хтось"), "дизайнерів без команди не чистимо: «не знаю» ≠ «нема»");
});

test("простір без дашборда: ключі словника екрана є в обох мовах", () => {
  for (const k of ["tasksIn", "newTask", "spaceEmpty", "spaceEmptyAgent"]) {
    assert.ok(DICT.uk[k] !== undefined && DICT.en[k] !== undefined, k);
    assert.equal(typeof DICT.en[k], typeof DICT.uk[k], k);
  }
});

test("англійською: «Tasks · P», «New task»", () => {
  setLang("en");
  try {
    const h = homeHTML(UI(), D_OFF());
    assert.match(h, /<h1 class="th-h">Tasks · P<\/h1>/);
    assert.match(h, /New task/);
    assert.match(h, /No tasks here yet/);
  } finally { setLang("uk"); }
});
