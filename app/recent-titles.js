/* Свіжі перейменування поверх запізнілої відповіді сервера.
   `render()` бере `/api/task` і `/api/tasks`; якщо перейменування встигло між початком запитів і
   відповіддю, відповідь несе СТАРУ назву. Перейменування, зроблені ПІСЛЯ початку запитів, мають
   перевагу; старші за початок сервер уже знає, їх не чіпаємо (тому тінь не стає постійною). */

/** Пам'ятаємо перейменування хвилину, не довше: далі від них нема користі. */
const KEEP_MS = 60000;

/** Повертає `{ task, list }` з назвами, виправленими за `renamedAt` (Map id → {title, at}); вхідні обʼєкти не мутує. */
export function applyRecentTitles(task, list, renamedAt, startedAt) {
  const fresh = (id) => {
    const r = renamedAt.get(id);
    return r && r.at > startedAt ? r.title : null;
  };
  const ft = task ? fresh(task.id) : null;
  const outTask = ft != null ? { ...task, title: ft } : task;
  let outList = list;
  if (list && Array.isArray(list.tasks)) {
    outList = { ...list, tasks: list.tasks.map((x) => { const f = fresh(x.id); return f != null ? { ...x, title: f } : x; }) };
  }
  return { task: outTask, list: outList };
}

/** Прибрати записи старші за хвилину. */
export function pruneRenamed(renamedAt, now) {
  for (const [id, r] of renamedAt) if (now - r.at > KEEP_MS) renamedAt.delete(id);
}
