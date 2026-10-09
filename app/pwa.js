/**
 * Сторінковий бік застосунку «Deai Canvas» (PWA): реєстрація service worker і
 * захоплення події встановлення. Підключає ЛИШЕ локальний інструмент (`app.js`);
 * оболонка опублікованих превʼю (`ext-shell.js`) його не імпортує й не повезе —
 * `pwa.js` нема в `SHELL_MODULES` (`serve.py`), це стереже `tests/pwa.test.mjs`.
 *
 * Вікно приходить параметром (`win`), а не береться з глобалу: так юніт у Node
 * підставляє подієве вікно й перевіряє захоплення `beforeinstallprompt` без
 * браузера. У бою — `window`.
 *
 * Що робить `beforeinstallprompt`. Chrome шле його, коли вважає сторінку
 * встановлюваною, і за замовчуванням показав би власний міні-банер. Ми
 * `preventDefault()` його ГЛУШИМО й тримаємо подію: єдиний шлях до встановлення —
 * пункт ⌘K «Встановити Deai Canvas як застосунок» (`shell-palette.js`). Жодних
 * нагадувань і підказок самих по собі (PRODUCT.md: інструмент, а не вебсервіс з
 * онбордингом). Подію можна використати ОДИН раз: після діалогу вона мертва,
 * тож `canInstall()` падає в `false`, поки Chrome не пришле нову. Виняток — відмова
 * через відсутність жесту (`NotAllowedError`): діалог ще не показувався, і подія
 * лишається придатною.
 */

/** Реєстрація worker: модуль зі scope `./` (тобто `/app/`). Відмову (приватне
 *  вікно, старий браузер, відкликаний дозвіл) ковтаємо — канвас працює і без
 *  worker, а втрата PWA-можливостей не варта банера про помилку.
 *
 *  `try/catch` потрібен ПОРУЧ із `.catch`: проміс ловить лише асинхронну відмову,
 *  а `navigator.serviceWorker` у пісочниці (sandboxed iframe, вимкнені cookies)
 *  кидає `SecurityError` уже на самому читанні геттера, і `register` може кинути
 *  синхронно. Необроблений виняток тут обірвав би `initPwa` — і разом із ним
 *  захоплення події встановлення, і весь `app.js`, який його кличе. */
function register(win) {
  try {
    const sw = win.navigator?.serviceWorker;
    if (!sw) return;
    sw.register("sw.js", { scope: "./", type: "module" }).catch(() => {});
  } catch (e) { /* див. вище */ }
}

/**
 * @param {object} opts
 * @param {Window} [opts.win] вікно (типово `window`).
 * @param {() => void} [opts.onInstalled] що зробити, коли застосунок встановлено
 *   (`appinstalled`) — `app.js` показує тост.
 * @returns {{canInstall: () => boolean, isStandalone: () => boolean,
 *   install: () => Promise<string>}}
 */
export function initPwa({ win = window, onInstalled = () => {} } = {}) {
  let deferred = null;
  let prompting = false;

  /* Не під час вантаження: реєстрація worker — фонова справа, і першому
     перемалюванню канваса вона не конкурент. */
  if (win.document?.readyState === "complete") register(win);
  else win.addEventListener("load", () => register(win), { once: true });

  win.addEventListener("beforeinstallprompt", (ev) => {
    ev.preventDefault();
    deferred = ev;
  });
  win.addEventListener("appinstalled", () => {
    deferred = null;
    onInstalled();
  });

  return {
    /** Є подія, яку ще можна використати. */
    canInstall: () => deferred !== null,
    /** Вікно вже встановленого застосунку: пропонувати встановлення нічого. */
    isStandalone: () => !!win.matchMedia?.("(display-mode: standalone)").matches,
    /** Показати системний діалог встановлення. Викликати з жесту користувача
     *  (клік, Enter) — інакше Chrome відхилить `prompt()`. Не кидає ніколи.
     *  Результат:
     *   · `accepted` / `dismissed` — відповідь людини в діалозі; подію витрачено;
     *   · `blocked` — Chrome відмовив через відсутність жесту (`NotAllowedError`);
     *     подію НЕ спалено — вона ще не показувала діалог, наступний жест спрацює;
     *   · `busy` — діалог уже відкритий (подвійний клік): другий `prompt()`
     *     кинув би `InvalidStateError` і спалив би подію;
     *   · `unavailable` — події нема; `error` — інша відмова (подію спалено). */
    async install() {
      const ev = deferred;
      if (!ev) return "unavailable";
      if (prompting) return "busy";
      prompting = true;
      try {
        await ev.prompt();
        const { outcome } = await ev.userChoice;
        deferred = null;
        return outcome;
      } catch (e) {
        if (e?.name === "NotAllowedError") return "blocked";
        deferred = null;
        return "error";
      } finally {
        prompting = false;
      }
    },
  };
}
