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

/**
 * Значення полів форми — ЧИСТА функція над переліком `{name, type, value, checked,
 * disabled}` (рівно те, що дає `form.elements`, тож у вузлі її можна прогнати без DOM).
 * Правила — ті самі, що в HTML-відправки: безіменні, вимкнені й кнопки пропускаються;
 * галочка — булеве (на відміну від HTML, де її нема в наборі, коли вимкнена: форма в
 * цьому канвасі хоче `false`, а не відсутність); радіо — значення вибраного, а коли
 * не вибрано жодного — ключа нема взагалі. `readonly` поле ЛИШАЄТЬСЯ (його значення —
 * відповідь сервера, яку людина лише не може міняти); `disabled` — ні.
 * Значення НЕ обрізаються: пробіли — справа викликача (назва простору обрізає, пароль
 * не мав би).
 */
export function formValues(fields) {
  const out = {};
  for (const f of Array.from(fields ?? [])) {
    if (!f || !f.name || f.disabled) continue;
    if (f.type === 'button' || f.type === 'submit' || f.type === 'reset') continue;
    if (f.type === 'checkbox') { out[f.name] = !!f.checked; continue; }
    if (f.type === 'radio') { if (f.checked) out[f.name] = String(f.value ?? ''); continue; }
    out[f.name] = String(f.value ?? '');
  }
  return out;
}

/**
 * Фокус-пастка для Tab у формі: куди перевести фокус, щоб він не втік за оверлей, або
 * `null` — хай іде своїм шляхом браузер. `index` — де фокус серед досяжних елементів
 * форми (`-1` — поза ними), `count` — скільки їх. Shift+Tab з першого (або ззовні) — на
 * останній, Tab з останнього (або ззовні) — на перший. Підкладка ловить кліки, але НЕ
 * клавіатуру: без пастки Tab із кнопки «Створити» йшов у смугу й макет ПІД діалогом.
 */
export function tabWrap(index, count, shift) {
  if (!(count > 0)) return null;
  if (shift) return index <= 0 ? count - 1 : null;
  return index < 0 || index >= count - 1 ? 0 : null;
}

/**
 * Куди повернути фокус, коли діалог закривається: перший ПРИДАТНИЙ з `candidates`
 * (відкривач, а за ним запасний, який дає викликач) або `null`.
 * `lost` — чи фокус «втрачено»: стояв усередині діалогу чи на `body` (вузол, що його мав,
 * зник). Якщо ж фокус уже ПЕРЕВЕДЕНО кудись поза діалог — продовження успіху (екран «Задачі»
 * ставить його на пошук, вихід з нього — на логотип), — чіпати його не можна: відкривач
 * тоді вже не той, що хоче людина. Придатний — підключений до документа, не схований
 * предком (`[hidden]`: екран «Задачі» ховається цілком) і не `body`/`html`: `body.focus()` нічого
 * не робить, але стояв би першим і не пустив до запасного.
 */
export function focusBackTarget(lost, candidates, usable = defaultUsable) {
  if (!lost) return null;
  return Array.from(candidates ?? []).find((el) => el && usable(el)) ?? null;
}
const defaultUsable = (el) => !!el.isConnected && !el.disabled && !/^(BODY|HTML)$/.test(el.tagName ?? '')
  && !el.closest?.('[hidden]');

/* Досяжні клавіатурою елементи форми. Не рахуються: схований (`hidden`, зокрема
   предком), вимкнений і з `tabindex=-1` — на них Tab не стане, і пастка вказала б у
   порожнечу. `-1` тут не крайній випадок: кружки кольору — roving tabindex, у Tab-порядку
   лише вибраний, а решта (теж `button`) мусять випасти з переліку. */
const TABBABLE = 'a[href],button,input:not([type=hidden]),select,textarea,[tabindex]';
const tabbables = (root) => [...root.querySelectorAll(TABBABLE)]
  .filter((el) => !el.disabled && el.tabIndex >= 0 && !el.closest('[hidden]'));

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
function overlay(text, kind, { value = '', readOnly = false, danger = false, yes = t('askOk'), details = [], choices = [], detailsLabel = '', form = null } = {}) {
  const cancelled = kind === 'yesno' ? false : (kind === 'tell' ? undefined : null);
  const isForm = kind === 'form';
  if (open) open.cancel();
  /* Відкривач — ПІСЛЯ `open.cancel()`: той, що закривається, щойно повернув фокус на свого
     відкривача, і саме його ми й успадковуємо (до скасування фокус стояв би в підкладці,
     якої за мить не стане). */
  const opener = document.activeElement;
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
    boxEl.className = isForm ? 'cv-ask cv-ask--form' : 'cv-ask';
    scrim.appendChild(boxEl);

    /* `<label>` лише там, де є що підписувати; у підтвердженні й повідомленні
       це абзац тексту, а не назва поля. У формі заголовок і підписи полів — у
       розмітці викликача (`form.build`), тож власного абзацу нема. */
    const head = isForm ? null : document.createElement(kind === 'ask' ? 'label' : 'p');
    if (head) {
      head.textContent = text;
      boxEl.appendChild(head);
    }

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
    /* У формі рядок кнопок НЕ додається в коробку: її кнопки — у розмітці викликача
       (поруч із полями, у тому порядку, що потрібен формі). Зібрані вище вони лишаються
       відчепленими й нікого не чіпають; не гілкувати їхнє створення — щоб рядок, який
       стережуть тести наявних діалогів, лишився дослівно тим самим. */
    if (!isForm) boxEl.appendChild(row);

    /* ФОРМА. Розмітку дає викликач (`form.build()`; усі дані в ній — через `esc`), а
       оболонка бере на себе рівно те, що в усіх решти діалогів: одиночність,
       підкладку, Esc, фокус-пастку. Відправка — НАТИВНА (`<form>` із
       `button[type=submit]`): Enter у полі й кнопка йдуть одним шляхом, без другого
       обробника клавіш. Діалог лишається відкритим, поки `onSubmit` не відповість
       «добре» — відмова сервера мусить бути видна ТАМ, де людина щойно набрала
       значення, а не тостом поверх закритого вікна. */
    let formEl = null;
    let busy = false;
    let ctl = null;
    if (isForm) {
      boxEl.innerHTML = form.build();
      formEl = boxEl.querySelector('form');
      const errEl = () => formEl.querySelector('[data-form-error]');
      ctl = {
        form: formEl,
        /* Текст помилки у слот `[data-form-error]` (`role="alert"` — читач озвучить
           сам). Порожній — ховає. */
        error(msg) {
          const el = errEl();
          if (!el) return;
          el.textContent = msg || '';
          el.hidden = !msg;
          /* Зняти відмову — зняти й `aria-invalid` з полів: стара помилка поля, яке людина
             вже правила, зчитувачу не потрібна. */
          if (!msg) for (const f of formEl.querySelectorAll('[aria-invalid]')) f.removeAttribute('aria-invalid');
        },
        /* Поле за імʼям — помилка про НЬОГО: `aria-invalid` (текст помилки поле вже
           знає з `aria-describedby` на `[data-form-error]`) і фокус. Виклик ПЕРЕД поверненням
           тексту: `error(текст)` потім `aria-invalid` не знімає. */
        focus(name) {
          const f = formEl.elements.namedItem(name);
          if (!f) return;
          f.setAttribute?.('aria-invalid', 'true');
          f.focus?.();
        },
        /* На час запиту «Створити» вимкнена, а форма позначена зайнятою: другий клік
           не створить другий простір. */
        busy(on) {
          for (const b of formEl.querySelectorAll('button[data-a="ok"]')) b.disabled = on;
          if (on) formEl.setAttribute('aria-busy', 'true'); else formEl.removeAttribute('aria-busy');
        },
      };
      formEl.addEventListener('submit', async (ev) => {
        ev.preventDefault();
        if (busy || open !== api) return;
        const values = formValues(formEl.elements);
        if (!form.onSubmit) { done(values); return; }
        busy = true;
        ctl.busy(true);
        ctl.error('');
        let err;
        try { err = await form.onSubmit(values, ctl); }
        catch (e) { err = t('errFailed', String(e?.message ?? e)); }
        busy = false;
        if (open !== api) return;     // оверлей перебито іншим питанням, поки летів запит
        ctl.busy(false);
        if (err) ctl.error(err); else done(values);
      });
      formEl.querySelector('[data-a="cancel"]')?.addEventListener('click', () => {
        if (!busy) done(cancelled);
      });
      /* Людина правила поле — стара відмова її більше не стосується. Програмні зміни
         (підстановка знайденого простору) `input` не викликають, їх це не зачіпає. */
      formEl.addEventListener('input', () => ctl.error(''));
    }
    document.body.appendChild(scrim);

    const done = (result) => {
      if (open !== api) return;      // уже закритий іншим шляхом
      open = null;
      /* Чи фокус «втрачено» — ДО зняття підкладки: після `remove()` вузол, що його мав,
         вже не в документі, і `activeElement` стане `body`, а різниці між «втратили» і
         «людина (чи продовження успіху) перевела його сама» не лишиться. */
      const a = document.activeElement;
      const lost = !a || a === document.body || scrim.contains(a);
      scrim.remove();
      document.removeEventListener('keydown', onKey, true);
      focusBackTarget(lost, [opener, form?.focusBack?.()])?.focus({ preventScroll: true });
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
      /* Поки форма чекає відповіді сервера, Esc її НЕ закриває: запит однаково
         долетить, і простір створився б за закритим вікном — без перемикання на
         нього. Подію гасимо, щоб вона не пішла закривати дропдаун під підкладкою. */
      if (e.key === 'Escape' && busy) { e.stopPropagation(); return; }
      if (e.key === 'Escape') { e.stopPropagation(); done(cancelled); return; }
      if (e.key === 'Tab' && formEl) {
        const list = tabbables(boxEl);
        const to = tabWrap(list.indexOf(document.activeElement), list.length, e.shiftKey);
        if (to !== null) { e.preventDefault(); list[to].focus(); }
        return;
      }
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
    else if (formEl) {
      form.onMount?.(formEl, ctl);
      /* `data-autofocus` — поле, з якого форма хоче почати; без нього — перше текстове. */
      const first = formEl.querySelector('[data-autofocus]')
        ?? formEl.querySelector('input:not([type=hidden])') ?? formEl.querySelector('button');
      first?.focus();
      if (first?.tagName === 'INPUT') first.select();
    } else ok?.focus();
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

/**
 * Форма з кількох полів — діалог простору й «Нова задача». Та сама оболонка, що в
 * решти (одиночний оверлей, підкладка, Esc, фокус-пастка), але тіло — розмітка від
 * `build()`, а результат — значення полів.
 *
 *   `build()`            рядок HTML УСЕРЕДИНІ коробки: один `<form>` з полями (`name=…`),
 *                        слотом `[data-form-error]`, кнопкою `button[type=submit][data-a=ok]`
 *                        і `button[data-a=cancel]`. Дані в розмітці — лише через `esc`.
 *   `onMount(form, ctl)` після вставки в DOM, ДО фокусу: тут викликач вішає свої
 *                        слухачі (кружки кольору, підказка про теку). Слухачі —
 *                        на вузлах форми, тож зникають разом із нею.
 *   `onSubmit(values, ctl)` асинхронна перевірка/запит. Повернула РЯДОК — це вже
 *                        перекладений текст помилки: діалог лишається відкритим,
 *                        рядок іде в `[data-form-error]`. Повернула нічого — успіх,
 *                        діалог закривається. Кинула — помилка показується так само
 *                        (`errFailed`). Без `onSubmit` відправка просто закриває діалог.
 *
 *   `focusBack()`        запасний відкривач для фокуса після закриття (вузол, що його мала
 *                        людина, міг бути перемальований: смуга міняє `innerHTML` цілком) —
 *                        викликається ПРИ закритті, тож бачить свіжий DOM. Фокус вертається
 *                        лише тоді, коли його справді втрачено (`focusBackTarget`).
 *
 * Повертає `values` (див. `formValues`) після успішної відправки, або `null` — Esc,
 * «Скасувати» чи оверлей, перебитий іншим питанням. `ctl` — `{form, error(текст),
 * focus(імʼя), busy(bool)}`.
 *
 * Свідомо БЕЗ клавіші Enter-на-документі, як у `ask`: у формі Enter відправляє її
 * нативно, а свій обробник перебивав би вибір людини на кнопці «Скасувати».
 */
export const askForm = (build, { onMount, onSubmit, focusBack } = {}) =>
  overlay('', 'form', { form: { build, onMount, onSubmit, focusBack } });
