/**
 * Локальний бекап коментатора не сміє тихо відмовляти (fb 05.11.2026).
 *
 * ЩО ЛАМАЛОСЬ. `_backupNow()` клав у localStorage ВЕСЬ список пінів — зі
 * знімком HTML і скріном у base64 — і нічого не витісняв. За кілька задач
 * origin канваса (~5 млн символів) забився: `blog` — 6 ключів по 370–450 КБ,
 * `boss-interface`, `graphScenarios`… Кожен наступний запис падав у `catch {}`
 * мовчки. Разом із впалим POST адаптера пін жив тільки в памʼяті вікна, і
 * перезавантаження стерло 5 пінів задачі `portfolio`.
 *
 * Як і сусідні тести, тягнемо чисті функції з джерела, сховище — підробка з
 * квотою, що кидає, як справжній `QuotaExceededError`.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)),
                         "..", "src", "comment-layer.js");
const src = readFileSync(SRC, "utf8");

const grab = (name) => {
  const m = src.match(new RegExp(` {2}function ${name}\\([\\s\\S]*?\\n {2}\\}`));
  assert.ok(m, `у comment-layer.js немає ${name}`);
  return m[0];
};
const prefix = src.match(/ {2}const BACKUP_PREFIX = [^\n]+/);
assert.ok(prefix, "у comment-layer.js немає BACKUP_PREFIX");
// eslint-disable-next-line no-new-func
const { lightPin, evictStaleBackups, writeBackup } = new Function(
  `${prefix[0]}\n${grab("lightPin")}\n${grab("evictStaleBackups")}\n${grab("writeBackup")}\n`
  + "return { lightPin, evictStaleBackups, writeBackup };")();

/** localStorage із квотою в символах (ключ + значення), як у Chrome. */
function quotaStore(limit, initial = {}) {
  const m = new Map(Object.entries(initial));
  const used = () => [...m].reduce((n, [k, v]) => n + k.length + v.length, 0);
  return {
    get length() { return m.size; },
    key: (i) => [...m.keys()][i] ?? null,
    getItem: (k) => (m.has(k) ? m.get(k) : null),
    removeItem: (k) => { m.delete(k); },
    setItem(k, v) {
      const prev = m.get(k);
      m.set(k, String(v));
      if (used() > limit) {
        if (prev === undefined) m.delete(k); else m.set(k, prev);
        const e = new Error("The quota has been exceeded."); e.name = "QuotaExceededError";
        throw e;
      }
    },
    _map: m,
  };
}

const KEY = "comment-layer:backup:dc/portfolio/local";
const heavy = (id, extra = {}) => ({
  id, text: `пін ${id}`, fp: { tag: "section" }, _pending: true,
  htmlSnapshot: { outerHTML: "<section>" + "x".repeat(50_000) + "</section>", text: "Hero" },
  meta: { seq: 1, shot: "data:image/jpeg;base64," + "A".repeat(50_000) },
  ...extra,
});

// 1. Порожній список — ключ прибрано (синхронізоване не лежить мертвим вантажем).
{
  const s = quotaStore(1e6, { [KEY]: "[{\"id\":\"old\"}]" });
  assert.equal(writeBackup(s, KEY, []), true);
  assert.equal(s.getItem(KEY), null, "після підтвердження ключ бекапу не прибрано");
}

// 2. Влазить — пишемо повністю, зі скріном.
{
  const s = quotaStore(1e6);
  assert.equal(writeBackup(s, KEY, [heavy("a")]), true);
  assert.ok(JSON.parse(s.getItem(KEY))[0].meta.shot, "повний бекап загубив скрін, хоч місце було");
}

// 3. Повний не влазить — легкий: текст і якір є, важкого нема.
{
  const s = quotaStore(60_000);
  assert.equal(writeBackup(s, KEY, [heavy("a")]), true, "легкий бекап не записався");
  const [pin] = JSON.parse(s.getItem(KEY));
  assert.equal(pin.text, "пін a");
  assert.deepEqual(pin.fp, { tag: "section" });
  assert.equal(pin._pending, true, "відновлення бере лише _pending — позначка загубилась");
  assert.equal("shot" in pin.meta, false);
  assert.equal("outerHTML" in pin.htmlSnapshot, false);
  assert.equal(pin.htmlSnapshot.text, "Hero", "легкий бекап викинув легкі поля знімка");
}

// 4. Дослівний стан 05.11: origin забитий мертвими ключами інших задач.
//    Мертві (без _pending) витісняються, живі чужі — лишаються легкими.
{
  const dead = JSON.stringify([{ id: "b1", text: "t", meta: { shot: "A".repeat(40_000) } }]);
  const alive = JSON.stringify([heavy("g1")]);
  const s = quotaStore(150_000, {
    "comment-layer:backup:dc/blog/local/x": dead,
    "comment-layer:backup:dc/graph/local": alive,
    "unrelated": "u".repeat(1000),
  });
  assert.equal(writeBackup(s, KEY, [heavy("a")]), true, "бекап не записався при забитому сховищі");
  assert.equal(s.getItem("comment-layer:backup:dc/blog/local/x"), null, "мертвий чужий ключ не витіснено");
  const g = JSON.parse(s.getItem("comment-layer:backup:dc/graph/local"));
  assert.equal(g[0].id, "g1", "чужий НЕсинхронізований пін витіснено — це втрата даних іншої задачі");
  assert.equal("shot" in g[0].meta, false, "чужий живий ключ не полегшено");
  assert.equal(s.getItem("unrelated"), "u".repeat(1000), "чіпнули чужий не-бекап ключ");
  assert.ok(JSON.parse(s.getItem(KEY))[0].meta.shot,
    "після чистки місця вистачало на повний бекап, а скрін усе одно викинуто");
}

// 5. Місця немає зовсім — `false`, а не мовчазний «успіх».
{
  const s = quotaStore(100);
  assert.equal(writeBackup(s, KEY, [heavy("a")]), false, "невдалий бекап удає успіх");
  assert.equal(writeBackup(null, KEY, [heavy("a")]), false, "без localStorage — теж не успіх");
}

// 6. Метод бекапу кладе ЛИШЕ _pending (відновлення інших і не бере).
{
  const m = src.match(/ {4}_backupNow\(\) \{[\s\S]*?\n {4}\},/);
  assert.ok(m, "немає _backupNow");
  assert.match(m[0], /filter\(\(c\) => c\._pending\)/, "_backupNow знову кладе весь список");
  assert.doesNotMatch(m[0], /catch \(e\) \{\}\s*\n\s*\},$/, "_backupNow знову ковтає помилку мовчки");
}

// 7. Оптимістичне сповіщення сховища не знімає позначку «не підтверджено».
{
  const m = src.match(/ {4}_onExternalChange\(external\) \{[\s\S]*?\n {4}\},/);
  assert.ok(m, "немає _onExternalChange");
  // eslint-disable-next-line no-new-func
  const method = new Function(`return { ${m[0].trim().replace(/,$/, "")} }`)()._onExternalChange;
  const layer = {
    comments: [{ id: "n", text: "новий", _pending: true }, { id: "s", text: "старий" }],
    _relocate() {}, _render() {},
  };
  method.call(layer, [{ id: "n", text: "новий" }, { id: "s", text: "старий" }]);
  const byId = Object.fromEntries(layer.comments.map((c) => [c.id, c]));
  assert.equal(byId.n._pending, true, "оптимістичне сповіщення зняло _pending — пін випаде з бекапу");
  assert.equal(byId.s._pending, undefined, "синхронізований пін став «неконфірмованим»");
  method.call(layer, [{ id: "s", text: "старий" }]);
  assert.ok(layer.comments.some((c) => c.id === "n"), "неконфірмований пін, якого нема у сховищі, загубився");
}

console.log("backup: ok");
