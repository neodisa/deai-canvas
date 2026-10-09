/**
 * Спільна фікстура живих тестів: тека задачі з однією ітерацією і двома
 * сторінками + сервер інструмента з цією текою.
 *
 * Файл НЕ `*.test.mjs` навмисно: `npm run test:live` бере `tests/live/*.test.mjs`,
 * і helper під таким іменем поїхав би в прогін окремим файлом без жодного тесту.
 */
import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");

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
 */
export async function startServer(taskDir, { portBase, extraTasks = {}, title = "Фікстура", profile = "", env = {}, root = ROOT }) {
  const cfgDir = mkdtempSync(path.join(tmpdir(), "dc-live-cfg-"));
  const tasksFile = path.join(cfgDir, "tasks.json");
  writeFileSync(tasksFile, JSON.stringify({
    current: "fixture", design_work_root: cfgDir,
    tasks: { fixture: { dir: taskDir, title, ...(profile ? { profile } : {}) }, ...extraTasks },
  }));
  // Number(), а не Math.floor(): Math.floor на BigInt кидає TypeError і тест упав
  // би ще до підняття сервера. Порт із хвоста годинника — щоб два живі тести не
  // сіли на один і той самий.
  const port = portBase + Number(process.hrtime.bigint() % 100n);
  const child = spawn("python3", [path.join(root, "app", "serve.py")], {
    cwd: root,
    env: { ...process.env, PORT: String(port), DC_TASKS_FILE: tasksFile, DC_NO_OVERVIEW: "1", ...env },
    stdio: "ignore",
  });
  const url = `http://127.0.0.1:${port}`;
  for (let i = 0; i < 60; i += 1) {
    try {
      const res = await fetch(`${url}/api/task`);
      if (res.ok) return { child, url };
    } catch {}
    await new Promise((done) => setTimeout(done, 250));
  }
  child.kill();
  throw new Error("сервер інструмента не піднявся");
}
