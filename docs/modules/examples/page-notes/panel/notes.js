// Tool panel: a note for the current page. No network, no frameworks — only `window.deai`.
const $ = (id) => document.getElementById(id);
const note = $("note"), save = $("save"), status = $("status");

let ctx = null;      // the last context from the core: {space, task, iteration, page, lang, theme}
let saved = "";      // the text stored on the server for the current page

// Key of the note: no page may be selected — then the shared key "_".
const key = (c) => ({ task: c.task.id, page: c.page ? c.page.id : "_" });
const say = (text) => { status.textContent = text; };

// Show the page from context `c` and load its note.
async function show(c) {
  ctx = c;
  $("title").textContent = c.page ? c.page.title : "Без сторінки";
  note.disabled = save.disabled = true;
  say("");
  try {
    const r = await deai.call("tool_load", key(c));
    if (ctx !== c) return;               // the page changed meanwhile
    saved = note.value = r.text;
    note.disabled = save.disabled = false;
  } catch (e) {
    say("Не вдалося завантажити: " + e.message);
  }
}

// Save the text for the page of `c`. The error is rethrown: the caller decides what to show.
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

// The core reports a page change. Before switching, save the previous page's unsaved note.
deai.on("context", async (c) => {
  if (ctx && note.value !== saved) {
    try { await store(ctx, note.value); } catch (e) { /* leave it: the new page is shown below */ }
  }
  show(c);
});

deai.ready.then((init) => show(init.context));
