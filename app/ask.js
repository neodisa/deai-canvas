/**
 * Діалоги канваса: поле вводу, підтвердження і повідомлення. Заміна `prompt()`,
 * `confirm()` і `alert()`.
 *
 * ⛔ КАНОНІЧНЕ пояснення, чому їх тут немає. Решта місць (тести, CHANGELOG,
 * спека) хай посилається сюди, а не переказує: три копії однієї причини
 * розійдуться, і розійдеться саме та, якої ніхто не перечитує.
 *
 * Усі три примітиви браузер уміє ВИМКНУТИ. Chrome після кількох діалогів
 * показує «Prevent this page from creating additional dialogues», і щойно
 * галочку поставлено — для цієї вкладки назавжди, до перезавантаження —
 * `prompt()` миттєво віддає `null`, `confirm()` віддає `false`, а `alert()` не
 * показує нічого. Код при цьому скрізь писав `if (!name) return;` і так само
 * коротко перевіряв відповідь `confirm` — тобто однаково ковтав «користувач
 * передумав» і «браузер не показав діалог». Симптом власника: натискаєш «додати сторінку»
 * або «видалити сторінку» — не відбувається нічого й не сказано нічого.
 * Відтворено живими прогонами 28.08.2026 (ввід) і 31.08.2026 (підтвердження та
 * повідомлення): під ударом сім місць вводу, три підтвердження — з них два
 * руйнівні — і двадцять повідомлень, серед яких усі `catch`-и «Не вдалося: …».
 * Ті двадцять ще й ОЗБРОЮВАЛИ ту галочку: показуються вони найчастіше.
 *
 * Тут другого стану не існує за побудовою: оверлей або в DOM, або його немає, і
 * це видно тесту.
 *
 * Контракти навмисно збігаються з примітивами, які вони замінили, — місця
 * виклику мінялись порядково: `ask` → `string | null`, `askYesNo` → `boolean`,
 * `tell` → нічого. Різниця рівно одна, і вона суттєва: наші троє АСИНХРОННІ, а
 * `prompt`/`confirm`/`alert` спиняли сторінку цілком. Наслідок — нижче, у
 * коментарі про підкладку, і він коштував двох Critical у ревʼю.
 */
import { t } from "./i18n.js";

/** Один оверлей на канвас: два питання одночасно — це вже помилка. */
let open = null;

/* Сталий id можна тримати саме тому, що оверлей у DOM завжди один (див. `open`
   вище). Він потрібен, щоб `<label>` показував НА поле: підпис, привʼязаний у
   нікуди, не фокусує поле кліком і не читається зчитувачем як його назва. */
const INPUT_ID = 'cv-ask-input';

/**
 * Спільне тіло всіх трьох. `kind`: `ask` — поле вводу, `yesno` — підтвердження,
 * `tell` — повідомлення, `choice` — вибір одного з кількох варіантів зі списком
 * того, що зачепить дія (видалення теки з вмістом).
 *
 * Значення відмови різне для різних питань, і саме тому воно тут окремою
 * змінною, а не `null` на всіх: для підтвердження це `false`, тобто «оверлей не
 * піднявся» ніколи не читається як «користувач підтвердив». Дефолт руйнівної
 * дії — не робити її.
 */
function overlay(text, kind, { value = '', readOnly = false, danger = false, yes = t('askOk'), details = [], choices = [], detailsLabel = '' } = {}) {
  const cancelled = kind === 'yesno' ? false : (kind === 'tell' ? undefined : null);
  if (open) open.cancel();
  return new Promise((resolve) => {
    /* ПІДКЛАДКА, а не самий лише прямокутник посеред екрана. Це не косметика:
       `prompt`/`confirm` спиняли сторінку, і між питанням та відповіддю змінити
       не можна було нічого. Наші не спиняють, і без підкладки канвас лишався
       живим під відкритим питанням: ревʼю відтворило, як дизайнер перемикає
       `#pp-itsel`, поки відкрите «Назва нової сторінки:», — і сторінка їде в
       ІНШУ ітерацію; і як натискання сусідньої кнопки перебиває відкрите
       питання, а старий `?? ''` перетворював те перебиття на «створюй».
       Підкладка прибирає обидва сценарії на рівні взаємодії. На рівні коду їх
       додатково прибирають самі викликачі: усе, що читається ПІСЛЯ `await`,
       вони знімають ДО нього (ідіома `freshen()`), бо коректність запису не
       сміє триматись на CSS. */
    const scrim = document.createElement('div');
    scrim.className = 'cv-ask-scrim';
    /* Клік по підкладці навмисно НЕ закриває: половина питань тут — руйнівні,
       а промах повз коробку не є відповіддю на «видалити?». Виходи явні: Esc і
       кнопка. */
    const boxEl = document.createElement('div');
    boxEl.className = 'cv-ask';
    scrim.appendChild(boxEl);

    /* `<label>` лише там, де є що підписувати; у підтвердженні й повідомленні
       це абзац тексту, а не назва поля. */
    const head = document.createElement(kind === 'ask' ? 'label' : 'p');
    head.textContent = text;
    boxEl.appendChild(head);

    /* Перелік того, що зачепить вибір, — над кнопками й під питанням: людина
       спершу читає, ЩО зникне, і лише потім обирає. */
    if (kind === 'choice' && details.length) {
      const ul = document.createElement('ul');
      ul.className = 'cv-ask-list';
      /* Список прокручується (до 160px), тож без tabindex клавіатурою його не
         дочитати; role/aria-label — щоб читач назвав, ЩО це за перелік. */
      ul.tabIndex = 0;
      ul.setAttribute('role', 'list');
      if (detailsLabel) ul.setAttribute('aria-label', detailsLabel);
      for (const d of details) {
        const li = document.createElement('li');
        li.textContent = d;           // textContent: назви сторінок — чужий текст
        ul.appendChild(li);
      }
      boxEl.appendChild(ul);
    }

    let input = null;
    if (kind === 'ask') {
      head.htmlFor = INPUT_ID;
      input = document.createElement('input');
      input.id = INPUT_ID;
      input.type = 'text';
      input.value = value;
      input.readOnly = readOnly;
      boxEl.appendChild(input);
    }

    /* Кнопки — окремим рядком, а не дітьми колонки: у колонці `flex-direction`
       поставив би «Скасувати» ПІД «Гаразд», двома сходинками одна над одною. */
    const row = document.createElement('div');
    row.className = 'cv-ask-row';
    const button = (a, label) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.dataset.a = a;
      b.textContent = label;
      row.appendChild(b);
      return b;
    };
    const okText = kind === 'tell' ? t('askGotIt')
      : (kind === 'yesno' ? yes : (readOnly ? t('askClose') : t('askOk')));
    /* У `choice` кнопки «Гаразд» нема: відповіддю є САМ вибраний варіант, а
       «Гаразд» поруч із двома дієсловами було б третім, безіменним. */
    const ok = kind === 'choice' ? null : button('ok', okText);
    if (ok && danger) ok.classList.add('cv-ask-danger');
    if (kind === 'choice') {
      for (const c of choices) {
        const b = button(c.a, c.label);
        if (c.danger) b.classList.add('cv-ask-danger');
        b.addEventListener('click', () => done(c.a));
      }
    }
    /* Повідомленню й режиму тільки-читання скасовувати нічого: там одна дія —
       закрити. Друга кнопка була б вибором без різниці. */
    const no = (kind === 'tell' || readOnly) ? null : button('cancel', t('askCancel'));
    boxEl.appendChild(row);
    document.body.appendChild(scrim);

    const done = (result) => {
      if (open !== api) return;      // уже закритий іншим шляхом
      open = null;
      scrim.remove();
      document.removeEventListener('keydown', onKey, true);
      resolve(result);
    };
    /* Слухач на `document`, а не на полі, і у фазі ЗАХОПЛЕННЯ. На documentі —
       щоб Esc працював і тоді, коли фокус усередині коробки перевели на кнопку.
       У capture — бо чужі слухачі клавіш ловлять саме так і саме Escape гасять:
       `vendor/inspector.js` і `comment-layer` вішають keydown у capture, і
       comment-layer ще й піднімається по `parent`, тобто сідає на вікно самого
       канваса. Bubbling-слухач після їхнього `stopPropagation` Esc не побачив
       би зовсім. У самій сторінці інструмента слухача клавіш сьогодні немає
       (перевірено пошуком) — capture тут запобіжник, а не латка. */
    const onKey = (e) => {
      if (e.key === 'Escape') { e.stopPropagation(); done(cancelled); return; }
      /* Enter підтверджує ЛИШЕ там, де фокус у полі вводу. У підтвердженні й
         повідомленні фокус стоїть на кнопці, і Enter натискає саме її — рідним
         шляхом браузера. Свій обробник там перебивав би вибір людини: на
         видаленні Enter означав би «видалити» навіть тоді, коли вона перевела
         фокус на «Скасувати». */
      if (e.key === 'Enter' && input) {
        e.stopPropagation();
        done(readOnly ? null : input.value);
      }
    };
    document.addEventListener('keydown', onKey, true);
    ok?.addEventListener('click', () => {
      if (kind === 'yesno') done(true);
      else if (kind === 'tell') done(undefined);
      else done(readOnly ? null : input.value);
    });
    no?.addEventListener('click', () => done(cancelled));

    const api = { cancel: () => done(cancelled) };
    open = api;
    /* Куди фокус: у поле — щоб одразу набирати (і щоб у режимі тільки-читання
       спрацював Ctrl+C по виділеному); на «Скасувати» — коли дія руйнівна, тож
       Enter і пробіл, натиснуті не дивлячись, скасовують, а не видаляють. */
    if ((danger || kind === 'choice') && no) no.focus();
    else if (input) { input.focus(); input.select(); }
    else ok?.focus();
  });
}

/** Ввід рядка. `null` — скасування (як у `prompt()`). */
export const ask = (question, value = '', { readOnly = false } = {}) =>
  overlay(question, 'ask', { value, readOnly });

/**
 * Підтвердження. `true` лише коли людина СКАЗАЛА «так»; будь-який інший вихід —
 * `false`. `danger` фарбує кнопку і ставить фокус на «Скасувати».
 */
export const askYesNo = (question, { yes = t('askOk'), danger = false } = {}) =>
  overlay(question, 'yesno', { yes, danger });

/**
 * Повідомлення, яке треба ПРОЧИТАТИ, — заміна `alert()`, не тоста. Тост гасне
 * за 3.2 с; сюди йде те, після чого дизайнер мусить щось зробити: «Не вдалося»,
 * «Позиція не збереглась», перелік незнятих кадрів.
 */
export const tell = (message) => overlay(message, 'tell');

/**
 * Вибір одного з варіантів. Повертає `a` обраного варіанта або `null` (Esc,
 * «Скасувати», оверлей перебито іншим питанням) — тобто «нічого не робити».
 * `details` — рядки списку під питанням; `choices` — `[{a, label, danger?}]`.
 * Фокус стоїть на «Скасувати»: Enter/пробіл не дивлячись не мають видаляти.
 */
export const askChoice = (question, { details = [], choices = [], detailsLabel = '' } = {}) =>
  overlay(question, 'choice', { details, choices, detailsLabel });
