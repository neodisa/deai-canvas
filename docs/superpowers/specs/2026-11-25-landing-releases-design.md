# Лендинг Deai Canvas, GitHub Releases і «підключи до свого AI»

Дата: 25.11.2026. Дві частини: **A** — розповсюдження (лендинг у репо, Pages, Releases, README); **B** — живий лендинг (анімації,
тур можливостей). A не чекає B. Код застосунку (`app/`), `CHANGELOG.md` і версія в `package.json` цією роботою не змінюються.

## Навіщо

Лендинг є, але лежить поза репо, не опублікований і не дає способу «взяти» Deai, крім промпта для агента. На GitHub лише теги,
без Releases, а як підключити Deai до свого AI, видно тільки з SETUP.md. Власник залишив на лендингу 9 пінів: бренд, версія,
анімації, тур можливостей.

## Рішення власника (25.11.2026)

- **Встановлення:** два шляхи — агент (промпт SETUP.md) і команда в Терміналі (macOS). DMG/.app не робимо: інсталяція не з git
  втрачає кнопку оновлення, а підпис і нотаризація потребують платного акаунта Apple.
- **Хостинг:** GitHub Pages з цього ж репо, `https://neodisa.github.io/deai-canvas/`. Свій домен — пізніше (`CNAME` + og-адреси).
- **Releases:** автоматично з 0.40.0; минулі версії не заповнюємо.
- **Робоча поверхня лендинга:** особиста задача канваса «Deai Canvas · лендинг» (простір Personal). Власник коментує там, агент
  кладе туди ітерації; затверджена ітерація копіюється в `landing/` і комітиться. Зворотного синку нема.
- **Заголовок:** «Design with AI.» згортається в «Deai Canvas» і повертається — по колу (прототип затверджено).
- Піни L#1–L#9 — у частинах A і B нижче; кожен закривається з приміткою, що зроблено.

## Канал оновлень — чому Releases безпечні

Оновлення в застосунку читає лише теги `vX.Y.Z` (`git ls-remote --tags`), підтягує тег і робить `merge --ff-only`
(`app/updater.py`). GitHub Release — сторінка поверх наявного тега, updater її не бачить. Правила:

- Release створюється лише на вже запушений тег (`gh release create --verify-tag`); тег з інтерфейсу GitHub не створюємо.
- Тег, коміт якого не в `main`, Release не отримує (updater однаково відмовив би з `diverged`).
- Архів «Source code (zip)», який GitHub додає сам, не оновлюється з застосунку — про це рядок у тексті кожного Release.

## Частина A — розповсюдження

### A1. `landing/` у репо

- Комітимо `landing/` (index.html, styles.css, site.js, README.md, `assets/`) і `ops/landing-shots.mjs` + `ops/landing-shots/`.
  PNG-оригінали (`landing/screenshots/`, 5,5 МБ) НЕ комітимо: WebP уже 2880 px. «Full-size» у лайтбоксі веде на WebP.
- **Превʼю посилання:** `og:title`, `og:description`, `og:url`, `og:image`, `twitter:card=summary_large_image` з абсолютними
  адресами на `neodisa.github.io/deai-canvas/`; `assets/og.png` 1200×630 (PNG — WebP не всі месенджери показують).
- **Бренд (L#4):** скрізь «Deai Canvas», а не «Canvas»: «Set up Deai Canvas», «In Deai Canvas, you…».
- **Мобільне меню:** до 760 px — кнопка меню в шапці, що відкриває Workflow / Modules / FAQ / GitHub; Esc і клік повз закривають.
  До 560 px «Get started» переходить із шапки в меню (у героя своя кнопка), у шапці лишаються Share і меню.
- **«Get started»** — дві вкладки:
  - «With your agent»: наявний промпт і кнопка копіювання;
  - «In Terminal (macOS)»: `git clone https://github.com/neodisa/deai-canvas.git ~/deai-canvas && cd ~/deai-canvas && bash ops/canvas-app/install.sh && ./start.command`;
    рядком нижче — Overview: `npm ci && npx playwright install chromium` (Node 20+).
  Під вкладками — «Connect your agent» у три пункти (той самий текст, що в README, A2).
- **FAQ про платформи:** «Made for macOS: the launcher, app icon and autostart. On Windows and Linux, run `app/serve.py`
  with Python 3.9+ and open it in Chrome or Edge as an app window. A one-command start on every OS is on the roadmap.»
- **Версія і Beta (L#3):** плашка `Beta` біля логотипа в шапці; у футері «v0.39.1 · Beta» з посиланням на `CHANGELOG.md`
  на GitHub (сторінка Releases для старих версій була б порожня). Версію вписує Pages-workflow під час деплою (A4); у файлі в репо —
  заглушка з поточною версією, щоб локальний перегляд не був порожнім. Запитів до GitHub з браузера відвідувача нема.
- **Share (L#7):** друга кнопка в шапці поруч із «Get started». Є `navigator.share` (телефон) — системне меню «Поділитися»;
  нема — копіює в буфер «Deai Canvas — a local workspace for reviewing what your AI agent designs. Check it out:
  https://neodisa.github.io/deai-canvas/» і показує «Link copied».

### A2. README — окремими комітами

- Розділ «Install» стає «Get started» з тими самими двома шляхами.
- Одразу за ним «Connect your agent»:
  1. Агенти: Claude Code, Codex або будь-який агент із доступом до файлів і термінала — вставити промпт.
  2. Що агент отримує в просторі: `AGENTS.md` з маршрутами й темами довідки; для Claude Code — `CLAUDE.md` і кнопка
     «Підключити» (Settings → AGENTS.md), що ставить Stop-хук: правки агента видно в історії як AI.
  3. Цикл: пін на елементі → агент читає піни → нова ітерація → агент закриває пін приміткою.
- Посилання на сайт у шапці README.

### A3. GitHub Releases

- `ops/release_notes.py` (stdlib): `release_notes.py vX.Y.Z [--changelog PATH]` → у stdout секція `## [X.Y.Z] — …` з
  `CHANGELOG.md` (без самого заголовка) + рядок про встановлення. Перевіряє: тег за `^v\d+\.\d+\.\d+$` (як `TAG_RE` updater-а),
  секція існує й не порожня, `package.json` на тезі має ту саму версію. Будь-яка розбіжність — код ≠ 0 і пояснення в stderr.
  Юніт-тести: `tests/test_release_notes.py`.
- `.github/workflows/release.yml`: `on: push: tags: ['v*.*.*']`; `permissions: contents: write`; checkout з `fetch-depth: 0`;
  перевірка `git merge-base --is-ancestor "$GITHUB_SHA" origin/main`; `release_notes.py` → файл; `gh release create "$TAG"
  --verify-tag --title "Deai Canvas X.Y.Z" --notes-file …`. Release з таким тегом уже є — крок пропускається, не падає.
- ⚠️ На тегах GitHub бере workflow із самого тегованого коміту: щоб 0.40.0 отримала Release сама, `release.yml` має бути в `main`
  раніше за релізний коміт 0.40. Інакше перший Release — вручну тим самим скриптом. Попередити сесію релізу 0.40.

### A4. GitHub Pages

- `.github/workflows/pages.yml`: `on: push` у `main` зі змінами `landing/**`, `ops/build_site.py` або самого workflow;
  `workflow_run` після workflow «Release» (оновити версію на сайті); `workflow_dispatch`. Не `push` тегів: середовище
  `github-pages` типово дозволяє деплой лише з `main`, а `workflow_run` іде в контексті `main`.
- `ops/build_site.py` (stdlib, з юніт-тестами) збирає `_site/` з `landing/` без `README.md` і вписує найбільший тег `vX.Y.Z`
  в елемент `[data-version]`; публікують `actions/upload-pages-artifact` + `actions/deploy-pages`.
- Разове налаштування репо: Settings → Pages → Source: GitHub Actions (власник сам або агент через `gh api` після «так»).

## Частина B — живий лендинг

Робиться ітераціями в задачі канваса; на сайт — після затвердження власником. Спільні правила руху: `prefers-reduced-motion` —
статичний стан; анімації на паузі поза екраном (IntersectionObserver) і у фоновій вкладці; на тач-пристроях — без hover-ефектів.

- **B1. Заголовок (L#1):** «Design with AI.» → «De» лишається, «sign with » і «.» стискаються справа наліво, «AI» стає «ai»,
  виростає « Canvas» → «Deai Canvas» (~2,3 с), тримається 2,6 с, згортається назад, пауза, знову. Скрінрідер завжди читає
  «Design with AI. Keep control.». Без JS — статичний текст. Прототип: `morph.js`/`morph.css`.
- **B2. Shimmer (L#6):** світла смуга проходить по «AI-first design workspace»; той самий ефект — на статусі «Agent is working…»
  у сцені B3. Власний CSS (`background-clip: text`), без коду з референса.
- **B3. Жива сцена першого екрана (L#6):** поверх знімка Northline: курсор підходить до поля дат → ставить пін → зʼявляється
  коментар «Make the date field wider» → в острівці «Agent is working…» → кадр переходить у наступну ітерацію з виправленим полем і
  закритим піном. Відео не робимо. Потрібен один додатковий знімок «після» (A-скрипт знімків + фікстура).
- **B4. Точкова сітка «магніт» (L#5):** власна реалізація на `<canvas>` (код textures.dev не беремо: ліцензія Pro-текстур
  забороняє публікацію в репо, а безкоштовні — MIT з обовʼязковою приміткою). Точки біля курсора злипаються, поле тягнеться до
  нього. Де: фон «сцени» першого екрана і блоку «Get started». Приглушено, у кольорах лендинга.
- **B5. Тур можливостей зі скролом (L#2, L#8, L#9):** галерея прилипає, кожен крок скролу перемикає вкладку; прогрес збоку;
  вкладки клікабельні; на телефоні й при reduced motion — звичайні вкладки. Кроки:
  1. Spaces & tasks — простори, екран задач, теги;
  2. Iterations — ітерації з нотатками, порівняння, позначка «в превʼю»;
  3. Overview — сітка знімків, ширини;
  4. Flow — екрани зі стрілками;
  5. Inspector — властивості, токени, запит на зміну;
  6. Comments — піни для AI (агент закриває приміткою) і для команди;
  7. Team preview — публікація, пароль, коментарі команди в превʼю.
  Нові знімки — тим самим `ops/landing-shots.mjs` на вигаданих Northline/Forma.

## Перевірки

- `python3 -B -m unittest tests.test_release_notes`; тест внутрішніх адрес зі списком заборонених слів.
- Лендинг: 375 px і десктоп без горизонтального скролу, консоль без помилок, вкладки й меню з клавіатури, reduced motion.
- Pages-збірка локально: той самий крок, що в workflow, дає `_site/` з вписаною версією.

## Окреме «так» власника

- На кожну публічну дію: пуш гілки, увімкнення Pages, перший Release.
- Один раз на задачу «Deai Canvas · лендинг»: класти туди нові ітерації, відповідати на піни й закривати їх.

## Поза обсягом

DMG/.app, запуск однією командою на Windows/Linux, Releases минулих версій, власний домен, відео.
