/**
 * Спільна фікстура живих тестів: тека задачі з однією ітерацією і двома
 * сторінками + сервер інструмента з цією текою.
 *
 * Файл НЕ `*.test.mjs` навмисно: `npm run test:live` бере `tests/live/*.test.mjs`,
 * і helper під таким іменем поїхав би в прогін окремим файлом без жодного тесту.
 */
import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync, realpathSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");

/** Вигадані адреса й ключ Supabase простору ЛІГА (4b-2): сервер бере їх з КОРЕНЯ старого `tasks.json`. Хост не існує, а
 *  сторінкові запити до нього перехоплює `_liga-supabase.mjs` — справжньої мережі й справжнього проєкту тут нема. */
export const LIGA_SUPABASE = Object.freeze({ supabase_url: "https://abcdefghijkl.supabase.co", supabase_key: "sb_publishable_test" });

/**
 * Тека задачі з однією ітерацією (`it1`) і двома сторінками (`holovna`, `poshuk`).
 *
 * @param {object} opts
 * @param {(pageId: string) => string} opts.html розмітка сторінки. Кожен тест дає
 *   свою: зʼємці потрібна сторінка зі спінером, лінивою картинкою й кареткою,
 *   канвасу — проста висока. Спільної «правильної» розмітки тут немає.
 * @param {string[]} [opts.pages] id сторінок. За замовчуванням дві, як і було.
 *   Інший НАБІР потрібен там, де перевіряється сам габарит світу: у сітці кадрів
 *   рівно стільки, скільки сторінок, тож «вписати все» у двосторінкової й
 *   восьмисторінкової задачі — це різні камери, і збіг не буде випадковим.
 */
export function taskFixture({ html, pages = ["holovna", "poshuk"] }) {
  const dir = mkdtempSync(path.join(tmpdir(), "dc-live-"));
  const it1 = path.join(dir, "iterations", "it1");
  for (const page of pages) {
    mkdirSync(path.join(it1, page), { recursive: true });
    writeFileSync(path.join(it1, page, "index.html"), html(page));
  }
  const NAMES = { holovna: "Головна", poshuk: "Пошук" };
  writeFileSync(path.join(it1, "pages.json"), JSON.stringify({
    pages: pages.map((id) => ({ id, name: NAMES[id] || id, published: true })),
  }));
  writeFileSync(path.join(dir, "iterations.json"), JSON.stringify({
    iterations: [{ id: "it1", date: "24.08.2026 12:00", note: "фікстура", published: true }],
  }));
  return { dir, it1 };
}

/**
 * Сервер інструмента на вільному порту з фікстурним tasks.json.
 *
 * @param {string} taskDir тека задачі (`dir` із `taskFixture`).
 * @param {object} opts
 * @param {number} opts.portBase база порту. Кожен тестовий файл передає СВОЮ:
 *   `node --test` крутить файли ПАРАЛЕЛЬНО, і спільна база дала б колізію портів
 *   між файлами, а її ціна — 15 секунд чекання й падіння з «сервер не піднявся».
 * @param {Record<string, {dir: string, title: string}>} [opts.extraTasks] ще
 *   задачі в реєстрі, крім `fixture`. Поточною лишається `fixture` — решта
 *   потрібна там, де перевіряється сам ПЕРЕМИКАЧ задач. Заводимо їх ТУТ, а не
 *   через `POST /api/task-new`: той тягнеться до дзеркала GitLab і робить
 *   `git_autocommit`, тобто мережа й чужий стан у живому тесті, а дає він задачу
 *   з однієї порожньої сторінки без `pages.json` — світ, у якому нема чого
 *   міряти.
 * @param {string} [opts.profile] напрямок задачі. Він і вибирає ДИЗАЙН-СИСТЕМУ,
 *   з якою інспектор звіряє значення (`?ds=` на тезі інспектора, `serve.py`):
 *   без нього звірки немає взагалі, і тест про вироки ДС зелено перевіряв би
 *   тишу. Типово порожній — тобто «напрямок невідомий», рівно як у старих
 *   фікстур, щоб жоден наявний живий тест не змінив поведінки.
 * @param {string} [opts.root] корінь інструмента, з якого піднімати сервер
 *   (теку з `app/serve.py`). Типово — цей чекаут. Окремий корінь потрібен там, де
 *   тест САМ ПРАВИТЬ файли застосунку, щоб побачити, чи дійде свіжа версія до
 *   браузера (`tests/live/pwa.test.mjs`: service worker не сміє кешувати код), —
 *   правити файли справжнього чекаута з тесту не можна.
 * @param {string} [opts.title] назва задачі. Типова коротка й нічого не тисне;
 *   довга потрібна там, де перевіряється сама ГЕОМЕТРІЯ крошки — назва, що не
 *   влазить, малювалась поверх сусідів, і на короткій фікстурі це не
 *   відтворюється взагалі.
 * @param {boolean} [opts.supabase] дописати в КОРІНЬ старого `tasks.json` (тобто в конфіг простору ЛІГА)
 *   `LIGA_SUPABASE` — без нього `/commented?ch=project` — локальна сторінка з приміткою `comments-unconfigured`.
 *   Типово вимкнено: увімкнений конфіг змушує сторінку каналу «Команда» йти до `abcdefghijkl.supabase.co`, а це
 *   мусить бути перехоплено в самому тесті (`hermeticLiga`). Змінні `SUPABASE_URL`/`SUPABASE_KEY` оточення розробника
 *   сервер у живих тестах НЕ бачить ніколи (їх гасить фікстура): справжній проєкт сюди не потрапить.
 * @param {Array<{name: string, color?: string, id?: string, legacy?: boolean,
 *   integrations?: boolean, tasks?: Record<string, {dir: string, title?: string, jira?: string}>}>} [opts.spaces]
 *   ПРОСТОРИ (Deai 1.0, етап 1). Опція змінює фікстуру цілком: `taskDir`,
 *   `extraTasks`, `title`, `profile` ігноруються (задачі кожного простору — у його
 *   `tasks`), а замість них зʼявляється ізольована машина:
 *   · тимчасові `HOME` і `DEAI_HOME`, і дочірній процес отримує саме їх, а не
 *     успадковані від користувача — справжній `~/.deai` тест не торкається;
 *   · реєстр `<DEAI_HOME>/spaces.json` пишеться заздалегідь (форма з `app/spaces.py`),
 *     якщо просторів є;
 *   · простір `legacy: true` живе у старому файлі (`DC_TASKS_FILE` = тимчасовий
 *     `tasks.json`) і за замовчуванням має інтеграції; решта — у власній теці з
 *     `space.json` і `tasks.json` і без інтеграцій (`integrations: true` вмикає);
 *   · старий файл пишеться ЛИШЕ коли є простір `legacy: true`: для `spaces: []` його
 *     нема зовсім — інакше міграція створила б простір, і привітання не зʼявилось би.
 *     З тієї ж причини `spaces: []` не пише й реєстр: порожня машина — це машина без
 *     `<DEAI_HOME>`, а не з порожнім реєстром (так вона виглядає до першого простору).
 *   Поточний — перший простір. Теку простору (не `legacy`) кладемо під тимчасовою
 *   домівкою, а запасну теку `legacy`-простору — теж під нею (`<HOME>/Liga`), щоб
 *   типова тека нового простору (`~/deai-work/<назва>`) з ними не перетиналась.
 *   Готовність сервера — опитування `/api/spaces` (на порожній машині `/api/task`
 *   відповідає 404, і чекання на нього не скінчилось би).
 *   · `legacyExtra` (лише з `spaces`) — ще ключі в корінь старого `tasks.json` простору `legacy` (поверх `supabase: true`): напр. `jira_base`
 *     з обліковими для тестів міграції ЛІГИ (4d-3a), якої без цих ключів нема що мігрувати;
 *   · `deaiDir` (лише з `spaces`) — імʼя теки `DEAI_HOME` під тимчасовою домівкою, типово `.deai`. Інше потрібне там, де сервер мігрує ЛІГУ
 *     за швом `DC_MIGRATE_LIGA=1`: `<HOME>/.deai` він вважає «справжнім» (HOME у процесі підмінено) і відмовляє;
 *   · `machine` — `{home, deaiHome, legacyFile, spaces}` з попереднього запуску: той самий диск, жодного нового запису машини
 *     (другий старт того самого дому: «міграція нічого не пише»). `spaces`/`legacyExtra` тоді ігноруються.
 *   Повертає ще `{home, deaiHome, legacyFile, spaces: [{id, name, path, legacy, integrations}]}`
 *   (`legacyFile` — куди сервер дивиться як на старий `tasks.json`; на порожній машині його ще
 *   нема, тест може покласти туди будь-що, зокрема зіпсований файл).
 */
export async function startServer(taskDir, { portBase, extraTasks = {}, title = "Фікстура", profile = "", env = {}, root = ROOT, spaces, supabase = false, legacyExtra = {}, machine = null, deaiDir = ".deai" }) {
  const cfgDir = mkdtempSync(path.join(tmpdir(), "dc-live-cfg-"));
  const tasksFile = machine ? machine.legacyFile : path.join(cfgDir, "tasks.json");
  const iso = machine ? { home: machine.home, deaiHome: machine.deaiHome, spaces: machine.spaces }
    : spaces ? isolatedMachine(spaces, tasksFile, { ...(supabase ? LIGA_SUPABASE : {}), ...legacyExtra }, deaiDir) : null;
  if (!iso) {
    writeFileSync(tasksFile, JSON.stringify({
      current: "fixture", design_work_root: cfgDir,
      /* 4d-4a: напрямок задачі рантайм читає лише з `track` (`profile` — старий ключ, його читає тільки межа `task-new`/реєстру): пишемо обидва,
         як записує ЛІГА після кроку `liga-4d4a`. */
      tasks: { fixture: { dir: taskDir, title, ...(profile ? { profile, track: profile } : {}) }, ...extraTasks },
      ...(supabase ? LIGA_SUPABASE : {}),
    }));
  }
  // Number(), а не Math.floor(): Math.floor на BigInt кидає TypeError і тест упав
  // би ще до підняття сервера. Порт із хвоста годинника — щоб два живі тести не
  // сіли на один і той самий.
  const port = portBase + Number(process.hrtime.bigint() % 100n);
  const child = spawn("python3", [path.join(root, "app", "serve.py")], {
    cwd: root,
    env: {
      ...process.env, PORT: String(port), DC_TASKS_FILE: tasksFile, DC_NO_OVERVIEW: "1",
      /* ⛔ Справжній Supabase розробника (оточення) не доходить до живого тесту: конфіг ЛІГИ — лише з файла фікстури. */
      SUPABASE_URL: "", SUPABASE_KEY: "",
      /* ⛔ Те саме для Jira: після 4d-2 ядро в ізольованому прогоні їх не читає, а пояс і підтяжки лишаються. */
      JIRA_EMAIL: "", JIRA_TOKEN: "",
      /* Лише з `spaces`: домівка й реєстр — тимчасові, а git не питає про особу
         (інакше `git commit` у теці нової задачі мовчки не відбувся б). */
      /* Окремо від того, що простір без інтеграцій «не ходить назовні» (це й перевіряють
         тести): якщо код колись піде до GitLab, дзеркало лягає у тимчасову теку, а `ssh`
         замінено на `false` — спроба провалиться на місці, а не постукає на справжній хост. */
      ...(iso ? {
        HOME: iso.home, DEAI_HOME: iso.deaiHome,
        DC_MIRRORS_DIR: path.join(iso.home, ".mirrors"), GIT_SSH_COMMAND: "false", GIT_TERMINAL_PROMPT: "0",
        GIT_AUTHOR_NAME: "Live", GIT_AUTHOR_EMAIL: "live@example.invalid",
        GIT_COMMITTER_NAME: "Live", GIT_COMMITTER_EMAIL: "live@example.invalid",
      } : {}),
      ...env,
    },
    stdio: "ignore",
  });
  const url = `http://127.0.0.1:${port}`;
  /* Готовність: з просторами — `/api/spaces` (`/api/task` на порожній машині 404);
     без — як було. */
  const probe = iso ? "/api/spaces" : "/api/task";
  for (let i = 0; i < 60; i += 1) {
    try {
      const res = await fetch(`${url}${probe}`);
      if (res.ok) return { child, url, tasksFile, ...(iso ? { home: iso.home, deaiHome: iso.deaiHome, spaces: iso.spaces, legacyFile: tasksFile } : {}) };
    } catch {}
    await new Promise((done) => setTimeout(done, 250));
  }
  child.kill();
  throw new Error("сервер інструмента не піднявся");
}

/**
 * Ізольована «машина» для опції `spaces`: тимчасові домівка й реєстр, файли
 * просторів. Нічого не запускає — лише пише диск; повертає шляхи.
 * Домівка — реальний шлях (`realpath`): macOS кладе `/var/folders/…` за симлінком
 * `/private/var`, а перевірки теки на сервері порівнюють обидва вигляди.
 */
function isolatedMachine(spaces, legacyFile, legacyExtra = {}, deaiDir = ".deai") {
  const home = realpathSync(mkdtempSync(path.join(tmpdir(), "dc-live-home-")));
  const deaiHome = path.join(home, deaiDir);
  const used = new Set();
  const out = spaces.map((sp, i) => {
    const slug = String(sp.name).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40);
    let id = sp.id || (slug || `space-${i + 1}`);
    while (used.has(id)) id = `${id}-${i + 1}`;
    used.add(id);
    const legacy = !!sp.legacy;
    const spPath = legacy ? path.join(home, "Liga") : path.join(home, "work", id);
    mkdirSync(spPath, { recursive: true });
    writeFileSync(path.join(spPath, "space.json"), JSON.stringify({ name: sp.name, color: sp.color || "space-1" }));
    const tasks = Object.fromEntries(Object.entries(sp.tasks || {})
      .map(([tid, tk]) => [tid, { dir: tk.dir, title: tk.title || tid, ...(tk.jira ? { jira: tk.jira } : {}) }]));
    const cfg = { current: Object.keys(tasks)[0], design_work_root: spPath, tasks, ...(legacy ? legacyExtra : {}) };
    if (legacy) writeFileSync(legacyFile, JSON.stringify(cfg));
    else writeFileSync(path.join(spPath, "tasks.json"), JSON.stringify(cfg));
    return { id, name: sp.name, path: spPath, legacy, integrations: sp.integrations ?? legacy };
  });
  /* Порожня машина — це машина БЕЗ `~/.deai` зовсім (так вона виглядає до першого
     простору), а не з порожнім реєстром: екран привітання стережуть саме її. */
  if (out.length) {
    mkdirSync(deaiHome, { recursive: true, mode: 0o700 });
    writeFileSync(path.join(deaiHome, "spaces.json"), JSON.stringify({
      version: 1, current: out[0].id,
      spaces: out.map(({ id, path: p, legacy, integrations }) => ({ id, path: p, legacy, integrations })),
    }));
  }
  return { home, deaiHome, spaces: out };
}
