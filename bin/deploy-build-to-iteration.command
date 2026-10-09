#!/bin/zsh
# Deploy a built Angular app into a Design Canvas iteration (multi-file support).
# Usage: ./deploy-build-to-iteration.command <dist/browser dir> <task> <iterationId>
# PREREQ: build with  ng build --configuration=complianceLU --base-href=/it-assets/<iterationId>/
set -e
DIST="$1"; TASK="$2"; IT="$3"
[ -z "$DIST" -o -z "$TASK" -o -z "$IT" ] && { echo "usage: $0 <dist/browser> <task> <itN>"; exit 1; }
# Тека призначення перевизначається змінною середовища, а не четвертим позиційним
# аргументом: скрипт ВИДАЛЯЄ файли, і зайвий позиційний слот перетворив би описку
# в перших трьох аргументах на мовчазну підміну цілі чистки. Плюс .command
# запускають подвійним кліком із Finder, де аргументів не передати, а сусідній
# python у цьому ж проєкті вже читає саме env (DC_TASKS_FILE, DC_MIRRORS_DIR).
DST="${DC_ITERATION_DIR:-$HOME/deai-work/$TASK/iterations/$IT}"
mkdir -p "$DST"

# ⛔ Застарілі хешовані бандли — ПРИБРАТИ ПЕРЕД копіюванням. Angular дає кожній
# збірці нове імʼя з контент-хешем (main-LSD7LDZH.js), тому `cp` лише ДОДАЄ файли:
# за одну сесію в it1 назбиралось 18 старих main-*.js по ~800 кБ, і всі вони їхали
# в GitLab та в publish/ (фідбек 25.08.2026).
# ⛔ Теку цілком НЕ чистимо: поруч зі збіркою живуть pages.json, .canvas-state.json,
# shots/ (кадри канваса), підтеки сторінок і рукотворні файли — це робота дизайнера.
# NULL_GLOB: без нього zsh на порожній теці кидає «no matches found» і скрипт із
# set -e падає ще до копіювання. Лишається ввімкненим до кінця — свідомо: нижній
# glob по i18n від цього тільки надійніший (LOCAL_OPTIONS тут не скоупить нічого).
setopt NULL_GLOB
stale=(); freed=0
for f in "$DST"/*; do
  # Підтеки сторінок і shots/ — не файли, отже поза грою в принципі.
  if [ ! -f "$f" ]; then continue; fi
  base="${f:t}"
  # (а) схоже на хешований бандл. Хеш — суцільний пробіг ВЕЛИКИХ літер і цифр від
  # 6 символів: так іменує збірка, руками так не називають (людські імена —
  # lowercase/kebab). Без цієї умови під ніж пішли б pages.json і рукотворні файли.
  if [[ ! "$base" =~ '^.+-[A-Z0-9]{6,}\.(js|css)$' ]]; then continue; fi
  # (б) і чого НЕМА в новій збірці. Умова несуча: без неї знесли б свіжий бандл
  # цієї ж збірки — той самий шаблон імені, але він якраз потрібен.
  if [ -e "$DIST/$base" ]; then continue; fi
  # Розмір читаємо ДО видалення; не прочитався — файл усе одно назвемо в звіті,
  # просто не додамо до суми (мовчазний пропуск заборонений).
  sz=$(stat -f%z "$f" 2>/dev/null) || sz=0
  rm -f "$f"
  stale+=("$base"); freed=$(( freed + sz ))
done
# Чистка мусить бути ВИДИМОЮ: дизайнер має пересвідчитись, що зник саме мотлох
# збірки, а не його файл. Мовчазне видалення гірше за жодне.
if (( ${#stale} )); then
  echo "✓ прибрано застарілих бандлів: ${#stale}, звільнено $(( (freed + 512) / 1024 )) кБ"
  for b in $stale; do echo "   − $b"; done
fi

cp -R "$DIST"/. "$DST"/
# canvas serves on localhost → app isLocal=false → reads ./assets/i18n/ (merged files live in local/)
[ -d "$DST/assets/i18n/local" ] && cp "$DST/assets/i18n/local/"*.json "$DST/assets/i18n/" 2>/dev/null || true
grep -q "/it-assets/$IT/" "$DST/index.html" && echo "✓ base-href ok" || echo "⚠ base-href NOT /it-assets/$IT/ — rebuild with --base-href=/it-assets/$IT/"
echo "✓ deployed → $DST  (open Design Canvas → iteration $IT)"
