#!/bin/bash
# Design Canvas — точка входу: підняти сервери, дочекатися, відкрити вікно.
# Викликають «Design Canvas.app» (клік) і LaunchAgent автостарту (--servers-only);
# обидва ставить install.sh поруч. Спека:
# docs/superpowers/specs/2026-10-09-canvas-app-design.md
#
# Змінні (для тестів і розробки):
#   CANVAS_URL    адреса канваса         (типово http://localhost:8765/app/)
#   CANVAS_WAIT   скільки секунд чекати  (типово 15)
#   CANVAS_START  чим піднімати сервери  (типово start.command цього чекауту)
#   CANVAS_MANIFEST  маніфест застосунку (типово app/manifest.webmanifest чекаута)
#   CANVAS_PWA_DIRS  де шукати шим встановленого застосунку, через «:» (типово
#                    ~/Applications/Chrome Apps.localized і така сама в /Applications)
# `--print-pwa-id` — лише надрукувати id застосунку «Deai Canvas» (див. нижче) і вийти.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
URL="${CANVAS_URL:-http://localhost:8765/app/}"
WAIT="${CANVAS_WAIT:-15}"
START="${CANVAS_START:-$HERE/../../start.command}"
MANIFEST="${CANVAS_MANIFEST:-$HERE/../../app/manifest.webmanifest}"
PWA_DIRS="${CANVAS_PWA_DIRS:-$HOME/Applications/Chrome Apps.localized:/Applications/Chrome Apps.localized}"
LOG="$HOME/Library/Logs/design-canvas.log"
SERVERS_ONLY=0
PRINT_PWA_ID=0
[ "${1:-}" = "--servers-only" ] && SERVERS_ONLY=1
[ "${1:-}" = "--print-pwa-id" ] && PRINT_PWA_ID=1

up() { [ "$(curl -s -o /dev/null -m 2 -w '%{http_code}' "$URL")" = "200" ]; }

# Вікно — лише на клік: автостарт іде з launchd при вході, там модалка нікому
# не потрібна, вистачить логу. Текст іде через argv, а не підстановкою в
# AppleScript — шлях з лапкою не зламає скрипт.
alert() {
  echo "$1: $2" >&2
  [ "$SERVERS_ONLY" = 1 ] && return 0
  osascript - "$1" "$2" >/dev/null 2>&1 <<'OSA'
on run argv
  display alert (item 1 of argv) message (item 2 of argv) as critical
end run
OSA
}

# Канвас уже відкритий у Chrome → вивести наперед, а не плодити вікна.
# Chrome не запущений — не чіпаємо його: `tell application` запустив би
# його з порожнім вікном. Відмова в дозволі Automation → порожній вивід,
# і викликач просто відкриє нове вікно.
focus_existing() {
  osascript - "$URL" "$STARTED" 2>/dev/null <<'OSA'
on run argv
  set u to item 1 of argv
  set freshServer to (item 2 of argv) is "1"
  if application "Google Chrome" is not running then return "none"
  tell application "Google Chrome"
    set wid to missing value
    repeat with w in windows
      set i to 0
      repeat with t in tabs of w
        set i to i + 1
        if wid is missing value and (URL of t) starts with u then
          set wid to id of w
          set ti to i
        end if
      end repeat
    end repeat
    if wid is missing value then return "none"
    -- ⛔ Лише через `window id`: `w` з `repeat with w in windows` — позиційне
    -- посилання («N-те вікно»), і після activate воно вказує вже на ІНШЕ
    -- вікно. 09.10.2026 так наперед виходило чуже вікно в ~половині
    -- прогонів (перевірено по z-порядку CoreGraphics), а скрипт звітував
    -- «focused».
    set cw to window id wid
    set active tab index of cw to ti
    -- Сервер піднявся щойно цим кліком — у вкладці, найімовірніше, сторінка
    -- помилки (після ребуту Chrome відновлює вікно раніше за сервер).
    -- Якщо сервер уже працював — не чіпаємо: там може бути незбережене.
    if freshServer then tell active tab of cw to reload
    if minimized of cw then set minimized of cw to false
    activate
    set index of cw to 1
    return "focused"
  end tell
end run
OSA
}

# ── Встановлений застосунок «Deai Canvas» (PWA) ──────────────────────────────
# Якщо його встановлено, клік відкриває САМЕ його (свій значок у Dock, свій пункт у
# ⌘Tab, а `launch_handler: focus-existing` з маніфесту виводить наперед уже
# відкрите вікно), інакше — `--app`-вікно нижче, як і було. Спека PWA, «Запускач».
#
# Як Chrome рахує id застосунку (components/webapps/docs/identifiers.md; код —
# web_app_helpers.cc + crx_file/id_util.cc):
#   ManifestId = `id` з маніфесту, розвʼязаний відносно ORIGIN start_url, без
#                фрагмента (нема `id` — це сам start_url);
#   id = SHA-256(SHA-256(ManifestId)) → перші 16 байт → hex → кожен знак 0–f
#        замінено на a–p.
# Хеш ДВІЧІ: другий — всередині crx_file::GenerateId. Перевірено на власному
# тестовому векторі Chromium (https://www.chromestatus.com/features →
# fedbieoalmbobgfjapopkghdmhgncnaa) і на 15 справжніх шимах Chrome. Одинарний хеш
# не збігається з жодним. Тест `tests/test_canvas_app.py` закріплює обидва.
pwa_app_id() {
  python3 - "$URL" "$MANIFEST" 2>/dev/null <<'PY'
import hashlib, json, sys
from urllib.parse import urljoin, urlsplit

page, manifest_path = sys.argv[1], sys.argv[2]


def spec(url):
    """Канонічний вигляд URL, як у GURL: схема й хост малими, типовий порт геть,
    без фрагмента."""
    u = urlsplit(url)
    port = u.port
    if port == {"http": 80, "https": 443}.get(u.scheme):
        port = None
    host = u.hostname.lower() + (f":{port}" if port else "")
    return f"{u.scheme.lower()}://{host}{u.path or '/'}" + (f"?{u.query}" if u.query else "")


with open(manifest_path, encoding="utf-8") as f:
    m = json.load(f)
# Маніфест лежить поруч зі сторінкою (`<link rel=manifest href=manifest.webmanifest>`);
# start_url розвʼязується відносно ЙОГО адреси, а `id` — відносно origin start_url.
start = urljoin(urljoin(page, "manifest.webmanifest"), m.get("start_url", "."))
origin = "{0.scheme}://{0.netloc}/".format(urlsplit(start))
manifest_id = spec(urljoin(origin, m["id"]) if "id" in m else start)
h = hashlib.sha256(hashlib.sha256(manifest_id.encode()).digest()).digest()[:16].hex()
print("".join(chr(ord("a") + int(c, 16)) for c in h))
PY
}

# Шим застосунку, який Chrome кладе при встановленні: `<Імʼя>.app` у
# `Chrome Apps.localized` з bundle id `com.google.Chrome.app.<id>` (у старих
# збірках `…app.<профіль>-<id>`). Шукаємо у файловій системі, а НЕ через `mdfind`:
# індекс Spotlight відстає після встановлення, а сам `mdfind` не обмежити за часом,
# тоді як запуск не сміє зависати. Кілька grep по кількох десятках Info.plist — це
# мілісекунди. Шим, а не `open -na "Google Chrome" --args --app-id=…`: шим сам знає
# свій профіль і потрібний Chrome (див. app_mode_loader_mac.mm), запускає Chrome,
# якщо той не працює, і відкривається так само, як з Dock чи Spotlight; а `--app-id`
# без `--profile-directory` у людини з кількома профілями відкрив би не той.
pwa_shim() {
  local id="$1" dir plist IFS=:
  [ -n "$id" ] || return 1
  for dir in $PWA_DIRS; do
    for plist in "$dir"/*.app/Contents/Info.plist; do
      [ -f "$plist" ] || continue
      if grep -qE "\.app\.([^<]*-)?${id}</string>" "$plist" 2>/dev/null; then
        printf '%s\n' "${plist%/Contents/Info.plist}"
        return 0
      fi
    done
  done
  return 1
}

if [ "$PRINT_PWA_ID" = 1 ]; then
  pwa_app_id
  exit 0
fi

STARTED=0
if ! up; then
  STARTED=1
  "$START" >/dev/null 2>&1   # ідемпотентний: живе не чіпає, лог веде сам
  tries=0
  until up; do
    tries=$((tries + 1))
    if [ "$tries" -gt $((WAIT * 2)) ]; then
      alert "Канвас не піднявся" "За ${WAIT} с $URL так і не відповів. Лог: $LOG"
      exit 1
    fi
    sleep 0.5
  done
fi

[ "$SERVERS_ONLY" = 1 ] && exit 0

# Встановлений застосунок — відкриваємо його. Не відкрився (шим зламано, Chrome
# відмовив) — НЕ блокуємо запуск: падаємо в `--app`-вікно нижче.
SHIM="$(pwa_shim "$(pwa_app_id)")"
if [ -n "$SHIM" ] && open "$SHIM" >/dev/null 2>&1; then
  exit 0
fi

# Без Chrome навіть не компілюємо `tell application "Google Chrome"`:
# osascript тоді відкриває діалог «Де Google Chrome?».
if open -Ra "Google Chrome" >/dev/null 2>&1; then
  [ "$(focus_existing)" = "focused" ] && exit 0
  # -n обовʼязковий: запущений Chrome без нього мовчки ігнорує --args.
  open -na "Google Chrome" --args --app="$URL"
else
  open "$URL"
fi
