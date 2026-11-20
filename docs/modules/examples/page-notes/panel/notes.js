// Панель інструмента: нотатка до поточної сторінки. Без мережі й фреймворків — лише `window.deai`.
const $ = (id) => document.getElementById(id);
const note = $("note"), save = $("save"), status = $("status");

let ctx = null;      // останній контекст від ядра: {space, task, iteration, page, lang, theme}
let saved = "";      // текст, що лежить на сервері для поточної сторінки

// Ключ нотатки: сторінка може бути не вибрана — тоді спільний ключ "_".
const key = (c) => ({ task: c.task.id, page: c.page ? c.page.id : "_" });
const say = (text) => { status.textContent = text; };

// Показати сторінку з контексту `c` і підвантажити її нотатку.
async function show(c) {
  ctx = c;
  $("title").textContent = c.page ? c.page.title : "Без сторінки";
  note.disabled = save.disabled = true;
  say("");
  try {
    const r = await deai.call("tool_load", key(c));
    if (ctx !== c) return;               // тим часом перейшли на іншу сторінку
    saved = note.value = r.text;
    note.disabled = save.disabled = false;
  } catch (e) {
    say("Не вдалося завантажити: " + e.message);
  }
}

// Зберегти текст у сторінку `c`. Помилка кидається далі: викликач вирішує, що показати.
async function store(c, text) {
  await deai.call("tool_save", { ...key(c), text });
  if (ctx === c) saved = text;
}

save.addEventListener("click", async () => {
  try {
    await store(ctx, note.value);
    say("");
    deai.toast("Збережено");
  } catch (e) {
    say("Не збережено: " + e.message);
  }
});

// Ядро повідомляє про зміну сторінки. Перш ніж перейти, зберігаємо несхоронену нотатку попередньої.
deai.on("context", async (c) => {
  if (ctx && note.value !== saved) {
    try { await store(ctx, note.value); } catch (e) { /* лишаємо як є: нижче покажемо нову сторінку */ }
  }
  show(c);
});

deai.ready.then((init) => show(init.context));
