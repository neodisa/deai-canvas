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

/**
 * Текст питання → `{title, body}` (етап В): перший рядок — заголовок картки, решта — пояснення під ним.
 * Двокрапка в кінці заголовка — спадок підписів поля (`'Нова назва сторінки:'`), у заголовку вона зайва.
 */
export function splitTitle(text) {
  const s = String(text ?? '');
  const i = s.indexOf('\n');
  const title = (i < 0 ? s : s.slice(0, i)).trim().replace(/:\s*$/, '');
  return { title, body: i < 0 ? '' : s.slice(i + 1).trim() };
}

const POP_GAP = 10;   // від якоря до картки
const POP_EDGE = 8;   // від картки до краю вікна

/**
 * Де стати поповеру (етап В). `a` — прямокутник якоря (`getBoundingClientRect()`), `w`×`h` — розмір картки,
 * `vw`×`vh` — вікно, `place` — бажане `'above'|'below'`. По горизонталі — центр над якорем, але не ближче
 * `POP_EDGE` до країв; не влазить із бажаного боку, а з другого влазить — перевертається; ніде — притискається.
 * `tip` — x хвостика відносно картки (на центр якоря), у межах картки з запасом 12 px.
 */
export function popPlace(a, w, h, vw, vh, place = 'below') {
  const cx = a.left + a.width / 2;
  const left = Math.max(POP_EDGE, Math.min(vw - w - POP_EDGE, cx - w / 2));
  const above = a.top - POP_GAP - h;
  const below = a.bottom + POP_GAP;
  let p = place === 'above' ? 'above' : 'below';
  if (p === 'above' && above < POP_EDGE && below + h <= vh - POP_EDGE) p = 'below';
  else if (p === 'below' && below + h > vh - POP_EDGE && above >= POP_EDGE) p = 'above';
  const top = p === 'above' ? Math.max(POP_EDGE, above) : Math.max(POP_EDGE, Math.min(vh - h - POP_EDGE, below));
  const tip = Math.max(12, Math.min(w - 12, cx - left));
  return { left: Math.round(left), top: Math.round(top), tip: Math.round(tip), place: p };
}

/* Сталий id можна тримати саме тому, що оверлей у DOM завжди один (див. `open`
   вище). Він потрібен, щоб `<label>` показував НА поле: підпис, привʼязаний у
   нікуди, не фокусує поле кліком і не читається зчитувачем як його назва. */
const INPUT_ID = 'cv-ask-input';
/* Заголовок картки — назва діалогу й поля для зчитувача; id сталий з тієї самої причини, що й `INPUT_ID`. */
const TITLE_ID = 'cv-ask-title';

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
function overlay(text, kind, { value = '', readOnly = false, danger = false, yes = t('askOk'), details = [], choices = [], detailsLabel = '', form = null, error = false } = {}) {
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
    /* Поповер (етап В): форма біля кнопки, якою її відкрили, без підкладки — макет під нею живий. Якоря нема,
       він схований чи відʼєднаний — звичайна модальна картка. */
    const anchorEl = isForm && form.anchor && form.anchor.isConnected && form.anchor.getClientRects().length
      ? form.anchor : null;
    const scrim = document.createElement('div');
    scrim.className = anchorEl ? 'cv-ask-pop' : 'cv-ask-scrim';
    /* Клік по підкладці навмисно НЕ закриває: половина питань тут — руйнівні,
       а промах повз коробку не є відповіддю на «видалити?». Виходи явні: Esc і
       кнопка. */
    const boxEl = document.createElement('div');
    boxEl.className = isForm ? (anchorEl ? 'cv-ask cv-ask--form cv-ask--pop' : 'cv-ask cv-ask--form') : 'cv-ask';
    scrim.appendChild(boxEl);

    /* Заголовок і пояснення (етап В): перший рядок тексту — `<h2>`, решта — абзац під ним (`splitTitle`).
       У формі заголовок — у розмітці викликача (`form.build`), тож тут нічого. */
    if (!isForm) {
      const { title, body } = splitTitle(text);
      const head = document.createElement('h2');
      head.className = 'cv-ask-title';
      head.id = TITLE_ID;
      if (error) {
        /* Іконка — `<use>` на спрайт оболонки, а не імпорт `icons.js`: `ask.js` їде в публічне превʼю й мусить
           тягнути лише `i18n.js`. Помилки (`tellError`) показує лише оболонка, де спрайт є. */
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('class', 'ico'); svg.setAttribute('width', '16'); svg.setAttribute('height', '16');
        svg.setAttribute('aria-hidden', 'true');
        const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
        use.setAttribute('href', '#i-warn');
        svg.appendChild(use);
        head.appendChild(svg);
      }
      head.appendChild(document.createTextNode(title));
      boxEl.appendChild(head);
      if (body) {
        const p = document.createElement('p');
        p.className = 'cv-ask-text';
        p.textContent = body;
        boxEl.appendChild(p);
      }
      boxEl.setAttribute('role', kind === 'tell' ? 'alertdialog' : 'dialog');
      boxEl.setAttribute('aria-modal', 'true');
      boxEl.setAttribute('aria-labelledby', TITLE_ID);
      if (error) boxEl.classList.add('cv-ask--error');
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
      input = document.createElement('input');
      input.id = INPUT_ID;
      input.setAttribute('aria-labelledby', TITLE_ID);
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
    let place = null; let onOutside = null; let onBlur = null;   // поповер (етап В), знімаються в `done`
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

    if (anchorEl) {
      /* Форма відгуку сама каже `aria-modal="true"`; поповер не модальний — макет під ним живий. */
      formEl?.removeAttribute('aria-modal');
      const tip = document.createElement('span');
      tip.className = 'cv-ask-tip';
      boxEl.appendChild(tip);
      place = () => {
        const r = popPlace(anchorEl.getBoundingClientRect(), boxEl.offsetWidth, boxEl.offsetHeight, innerWidth, innerHeight, form.place);
        boxEl.style.left = `${r.left}px`;
        boxEl.style.top = `${r.top}px`;
        boxEl.dataset.place = r.place;
        tip.style.left = `${r.tip}px`;
      };
      place();
      addEventListener('resize', place);
      /* Клік повз картку — відповідь «скасовано», як Esc. Клік по самому якорю теж закриває, і той самий клік
         НЕ мусить відкрити форму знову: гасимо його одноразовим слухачем у capture на якорі (знімаємо за 600 мс,
         якщо pointerdown так і не став кліком — перетягування). Під час відправки (`busy` / `aria-busy`) — нічого. */
      onOutside = (e) => {
        if (boxEl.contains(e.target)) return;
        if (busy || formEl?.getAttribute('aria-busy') === 'true') return;
        if (anchorEl.contains(e.target)) {
          const swallow = (ev) => { ev.stopImmediatePropagation(); ev.preventDefault(); };
          anchorEl.addEventListener('click', swallow, { capture: true, once: true });
          setTimeout(() => anchorEl.removeEventListener('click', swallow, { capture: true }), 600);
        }
        done(cancelled);
      };
      document.addEventListener('pointerdown', onOutside, true);
      /* Клік у макет — це клік в iframe: до `document` оболонки він не долітає, зате вікно оболонки втрачає фокус.
         Ловимо `blur` і перевіряємо, що фокус пішов саме в рамку (а не в інше вікно ОС). */
      onBlur = () => setTimeout(() => {
        if (document.activeElement?.tagName !== 'IFRAME') return;
        if (busy || formEl?.getAttribute('aria-busy') === 'true') return;
        done(cancelled);
      }, 0);
      addEventListener('blur', onBlur);
    }

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
      if (onOutside) document.removeEventListener('pointerdown', onOutside, true);
      if (onBlur) removeEventListener('blur', onBlur);
      if (place) removeEventListener('resize', place);
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
      place?.();   // розмір картки міг змінитись після `onMount`
      /* `data-autofocus` — поле, з якого форма хоче почати; без нього — перше текстове. */
      const first = formEl.querySelector('[data-autofocus]')
        ?? formEl.querySelector('input:not([type=hidden])') ?? formEl.querySelector('button');
      first?.focus();
      if (first?.tagName === 'INPUT') first.select();
    } else ok?.focus();
  });
}

/**
 * Помилка дії (етап В): заголовок «що не вдалося», під ним причина (рядок сервера), іконка `warn`.
 * Замість `tell(t('errFailed', e.message))` там, де відомо, ЩО саме не вдалося.
 */
export const tellError = (title, reason) => overlay(`${title}\n${reason ?? ''}`, 'tell', { error: true });

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
 *   `anchor`             кнопка-якір (етап В): є — поповер біля неї без підкладки, нема чи схована — модальна картка.
 *   `place`              `'above'|'below'` — де від якоря стати (`popPlace`).
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
export const askForm = (build, { onMount, onSubmit, focusBack, anchor = null, place = 'below' } = {}) =>
  overlay('', 'form', { form: { build, onMount, onSubmit, focusBack, anchor, place } });
