/**
 * Навігація оболонки (0.40): власний стек Назад/Вперед + запис місця в адресу. Залежності (вікно, місце, «веди в місце») приходять
 * ззовні — модуль не знає про `app.js` і тестується на фальшивому вікні.
 *
 * ⛔ НЕ історія браузера. Кожне присвоєння `frame.src` і кожен перехід за посиланням у макеті додають запис у ЗАГАЛЬНУ історію
 * сеансу вікна, тож `history.back()/go()` ходило б спершу по записах iframe. Адреса лише ОПИСУЄ місце (`replaceState`, ніколи
 * `pushState`), а Назад/Вперед — `entries[]` + `index` тут.
 *
 *  · `sync()` — ЄДИНЕ місце запису адреси. Запис у стек — лише під ЖЕТОНОМ (`open()`/`close()`): дія-перехід відкриває його на
 *    мутації стану, перший `sync()` під ним записує рівно один запис і спалює жетон, `close()` у `finally` знімає. Ні ранній
 *    вихід, ні сторонній `render()` жетона не споживають і не лишають.
 *  · Поки працює `goTo` із цього модуля, `sync()` стримано (`held`): проміжні записи з `enterHome`/`wiz.requestExit` не
 *    затирають місця призначення; наприкінці стек осідає ОДИН раз із фінальним нормалізованим місцем (`settle`).
 *  · `goTo` → `true` | `false` (відмова, індекс лишається) | `'gone'` (задачі нема: запис викидаємо й ідемо до сусіднього).
 *  · Стек живе в `store` (sessionStorage); на старті місце з адреси, що відрізняється від збереженого поточного запису
 *    (глибоке посилання), додається новим записом.
 */
import { formatLocation, parseLocation } from "./location-model.js";

export const NAV_CAP = 100;

export function createNav({ win, store = null, getLoc, goTo, onChange = () => {}, cap = NAV_CAP }) {
  const norm = (loc) => formatLocation(loc);
  const urlOf = (hash) => `${win.location.pathname}${win.location.search}${hash}`;
  let entries = [];
  let index = 0;
  let held = 0;
  let token = null;
  let chain = Promise.resolve();

  const load = () => {
    try {
      const o = JSON.parse(store?.get?.() ?? "null");
      if (o && Array.isArray(o.entries) && o.entries.length && o.entries.every((x) => typeof x === "string")
        && Number.isInteger(o.index) && o.index >= 0 && o.index < o.entries.length) return o;
    } catch (e) { /* зіпсоване — починаємо з нуля */ }
    return null;
  };
  const save = () => { try { store?.set?.(JSON.stringify({ entries, index })); } catch (e) { /* без сховища стек живе до перезавантаження */ } };
  const trim = () => { while (entries.length > cap) { entries.shift(); index -= 1; } if (index < 0) index = 0; };
  const write = (hash) => { if (win.location.hash !== hash) win.history.replaceState(win.history.state, "", urlOf(hash)); };

  const startHash = norm(parseLocation(win.location.hash));
  const saved = load();
  if (saved) {
    entries = saved.entries.slice();
    index = saved.index;
    if (startHash && entries[index] !== startHash) { entries.splice(index + 1); entries.push(startHash); index = entries.length - 1; trim(); }
  } else {
    entries = [startHash];
  }
  save();

  const flags = () => `${index > 0}|${index < entries.length - 1}`;
  let shown = flags();
  const notify = () => { const f = flags(); if (f !== shown) { shown = f; onChange(); } };

  /** Місце осіло: поточний запис = фінальне нормалізоване місце; адреса — те саме. */
  function settle() {
    const h = norm(getLoc());
    entries[index] = h;
    write(h);
    save();
    notify();
  }
  function append(h) {
    entries.splice(index + 1);
    entries.push(h);
    index = entries.length - 1;
    trim();
  }

  function open() { token = { used: false }; return token; }
  function close(tk) { if (token === tk) token = null; }

  function sync() {
    if (held) return;
    const h = norm(getLoc());
    if (token && !token.used) {
      token.used = true;
      if (h !== entries[index]) { append(h); write(h); save(); notify(); return; }
    }
    if (h !== entries[index]) { entries[index] = h; save(); }
    write(h);
    notify();
  }
  /** Зафіксувати поточне місце як перехід негайно (дії, що не роблять `render()`, напр. вибір сторінки в «Огляді»). */
  function record() { const tk = open(); sync(); close(tk); }

  const run = (task) => { const p = chain.then(task, task); chain = p.catch(() => {}); return p; };
  const lead = async (loc) => {
    held += 1;
    try { return await goTo(loc); } catch (e) { return false; } finally { held -= 1; }
  };

  function step(dir) {
    return run(async () => {
      token = null;   // жетон дії, що не встигла закритись, не вмикає запис під час Назад/Вперед
      for (;;) {
        const to = index + dir;
        if (to < 0 || to >= entries.length) return false;
        const r = await lead(parseLocation(entries[to]));
        if (r === true) { index = to; settle(); return true; }
        if (r === "gone") {
          entries.splice(to, 1);
          if (dir < 0) index -= 1;
          save(); notify();
          continue;
        }
        settle();   // відмова: стан міг зсунутись (скасований діалог) — місце осідає як є, індекс той самий
        return false;
      }
    });
  }

  /* `hashchange`, що прийшов під час `goTo`, не губиться: `run` ставить його в чергу. Вписане місце знімаємо СИНХРОННО в мить події
   * (осідання попереднього переходу перепише адресу), а виконуємо вже після нього. */
  win.addEventListener("hashchange", () => {
    const typed = win.location.hash;
    run(async () => {
      token = null;
      const h = norm(parseLocation(typed));
      if (!h) { write(entries[index]); return; }   // порожня адреса (стерли hash): повертаємо поточне місце
      if (h === entries[index]) return;
      const r = await lead(parseLocation(h));
      if (r === true) {
        const now = norm(getLoc());
        if (now !== entries[index]) append(now); else entries[index] = now;
        write(now); save(); notify();
      } else {
        write(entries[index]);   // відмова чи такого місця нема — адреса вертається
      }
    });
  });

  return {
    open, close, sync, record,
    canBack: () => index > 0,
    canFwd: () => index < entries.length - 1,
    back: () => step(-1),
    forward: () => step(1),
    entries: () => entries.slice(),
    index: () => index,
  };
}
