#!/bin/bash
# Ставить точку входу в канвас: «Design Canvas.app» (Spotlight, Dock) +
# автостарт серверів при вході в систему. Логіка кліку — у launch.sh поруч;
# у .app лише запускач, тож після `git pull` перевстановлювати не треба.
#
# Запускати З ТЕРМІНАЛА основного чекауту: вшиває поточний PATH (nvm, python з
# /Library/Frameworks), якого не бачать ні Dock, ні launchd.
#
#   bash ops/canvas-app/install.sh              поставити / оновити
#   bash ops/canvas-app/install.sh --check      перевірити
#   bash ops/canvas-app/install.sh --uninstall  прибрати
#   bash ops/canvas-app/install.sh --replace <bundle-id>
#                                             зняти старий застосунок з ТОЧНО цим bundle id
#                                             (і його автостарт <id>.autostart), поставити цей
#
# Змінні (тести/розробка): CANVAS_APP_DIR (типово ~/Applications),
# CANVAS_AGENTS_DIR (~/Library/LaunchAgents), CANVAS_LSREGISTER,
# CANVAS_ALLOW_WORKTREE=1 — дозволити встановлення з git-ворктрі,
# DEAI_WORK_DIR — тека живих джерел для :4317; запікається і в автостарт, і в запускач .app
# (щоб клік по іконці піднімав сервери з тією самою текою). Лише абсолютний шлях без керівних
# символів, інакше ключа нема і буде попередження (start.command візьме ~/deai-work).
# DEAI_PORT НЕ запікається: бойовий порт фіксований (8765), DEAI_PORT — лише для ізольованих запусків.
# Спека: docs/superpowers/specs/2026-10-09-canvas-app-design.md
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SELF="$HERE/install.sh"
LAUNCH="$HERE/launch.sh"
ICON="$HERE/DesignCanvas.icns"
PKG="$HERE/../../package.json"
BUNDLE_ID="app.deai.designcanvas"
LABEL="$BUNDLE_ID.autostart"
APP_DIR="${CANVAS_APP_DIR:-$HOME/Applications}"
APP="$APP_DIR/Design Canvas.app"
INFO="$APP/Contents/Info.plist"
AGENTS_DIR="${CANVAS_AGENTS_DIR:-$HOME/Library/LaunchAgents}"
PLIST="$AGENTS_DIR/$LABEL.plist"
AGENT_LOG="$HOME/Library/Logs/design-canvas-autostart.log"
DOMAIN="gui/$(id -u)"
CANVAS_URL="${CANVAS_URL:-http://localhost:8765/app/}"
LSREGISTER="${CANVAS_LSREGISTER:-/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Versions/A/Support/lsregister}"

# Значення ключа з plist або порожньо (нема файлу, битий, не рядок).
plist_get() {
  python3 - "$1" "$2" 2>/dev/null <<'PY' || true
import plistlib, sys
try:
    with open(sys.argv[1], 'rb') as f:
        v = plistlib.load(f).get(sys.argv[2], '')
except Exception:
    v = ''
print(v if isinstance(v, str) else '')
PY
}

ours() { [ "$(plist_get "$INFO" CFBundleIdentifier)" = "$BUNDLE_ID" ]; }

# Чи знайдеться команда $2 з PATH=$1. Підоболонка + hash -r: інакше bash
# відповість зі свого кешу шляхів, а не з переданого PATH.
in_path() { (PATH="$1"; hash -r; command -v "$2") >/dev/null 2>&1; }

# Git-ворктрі: власний --git-dir ≠ спільний --git-common-dir.
in_worktree() {
  local dirs
  dirs="$(git -C "$HERE" rev-parse --path-format=absolute --git-dir --git-common-dir 2>/dev/null)" || return 1
  [ "$(printf '%s\n' "$dirs" | sed -n 1p)" != "$(printf '%s\n' "$dirs" | sed -n 2p)" ]
}

do_check() {
  local bad=0 launch path
  if [ ! -d "$APP" ]; then
    echo "✗ нема $APP — постав: bash \"$SELF\""; bad=1
  elif ! ours; then
    echo "✗ $APP — не наш застосунок (bundle id не $BUNDLE_ID)"; bad=1
  else
    launch="$(plist_get "$INFO" LigaCanvasLaunch)"
    path="$(plist_get "$INFO" LigaCanvasPath)"
    if [ -n "$launch" ] && [ -f "$launch" ]; then
      echo "✓ застосунок → $launch"
    else
      echo "✗ застосунок вказує на $launch, а його нема — перевстанови з основного чекауту"; bad=1
    fi
    if in_path "$path" python3; then
      echo "✓ python3 у вшитому PATH"
    else
      echo "✗ python3 у вшитому PATH нема — перевстанови з термінала"; bad=1
    fi
    if in_path "$path" node; then
      echo "✓ node у вшитому PATH"
    else
      echo "⚠ node у вшитому PATH нема — публікація превʼю не піде; перевстанови з термінала, де є node"
    fi
  fi
  if [ -f "$PLIST" ] && launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
    # macOS 13+: «Обʼєкти входу» вимикають агента, а launchctl print його ще
    # бачить. Here-string, а не пайп у grep -q: з pipefail ранній вихід grep
    # дав би SIGPIPE і «не вимкнено».
    local disabled
    disabled="$(launchctl print-disabled "$DOMAIN" 2>/dev/null || true)"
    if grep -qF "\"$LABEL\" => disabled" <<<"$disabled" || grep -qF "\"$LABEL\" => true" <<<"$disabled"; then
      echo "✗ автостарт вимкнено в Системні параметри → Загальні → Обʼєкти входу (там він — «bash»): увімкни"; bad=1
    else
      echo "✓ автостарт при вході завантажений ($LABEL)"
    fi
  else
    echo "✗ автостарт не завантажений ($LABEL) — перевстанови або глянь Системні параметри → Загальні → Обʼєкти входу"; bad=1
  fi
  return $bad
}

do_uninstall() {
  launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
  rm -f "$PLIST"
  if [ -e "$APP" ]; then
    if ! ours; then
      echo "✗ $APP — не наш застосунок (bundle id не $BUNDLE_ID), не чіпаю." >&2
      exit 1
    fi
    rm -rf "$APP"
  fi
  echo "🛑 Design Canvas.app і автостарт прибрано. Сервери, якщо працюють, лишились — ./stop.command."
}

# Зворотний DNS: щонайменше дві мітки, без порожніх, без дефіса першим; і не наш власний id.
valid_bundle_id() {
  local re='^[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$'
  [[ "$1" =~ $re ]] && [[ "$1" != -* ]] && [ "$1" != "$BUNDLE_ID" ]
}

# --replace <старий bundle id>: знімає застосунок із ТОЧНО цим id і його агента `<id>.autostart`.
# Застосунок з іншим id не чіпає (далі do_install відмовить «не наш»).
replace_old() {
  local old="$1" label="$1.autostart" cur
  if [ -e "$APP" ]; then
    cur="$(plist_get "$INFO" CFBundleIdentifier)"
    if [ "$cur" = "$old" ]; then
      launchctl bootout "$DOMAIN/$label" >/dev/null 2>&1 || true
      rm -f "$AGENTS_DIR/$label.plist"
      rm -rf "$APP"
      echo "↻ знято старий застосунок ($old) і його автостарт"
    fi
  else
    # Застосунку нема, а агент міг лишитись — прибираємо тільки його.
    launchctl bootout "$DOMAIN/$label" >/dev/null 2>&1 || true
    rm -f "$AGENTS_DIR/$label.plist"
  fi
}

do_install() {
  local replace_id="${1:-}"
  if ! command -v python3 >/dev/null 2>&1; then
    echo "✗ нема python3 у PATH — канвас без нього не працює." >&2
    exit 1
  fi
  if [ ! -f "$LAUNCH" ]; then
    echo "✗ нема $LAUNCH" >&2
    exit 1
  fi
  if in_worktree && [ "${CANVAS_ALLOW_WORKTREE:-}" != 1 ]; then
    echo "✗ $HERE — у git-ворктрі: застосунок вказував би на теку, яку потім знесуть." >&2
    echo "  Запусти з основного чекауту (для розробки — CANVAS_ALLOW_WORKTREE=1)." >&2
    exit 1
  fi
  # Чужий застосунок на нашому місці — відмова. Виняток: його id = той, що просили замінити (--replace).
  if [ -e "$APP" ] && ! ours && [ "$(plist_get "$INFO" CFBundleIdentifier)" != "$replace_id" ]; then
    echo "✗ $APP уже є, і це не наш застосунок — не перезаписую." >&2
    exit 1
  fi

  # Версія — з package.json у корені клону; нема/битий → 0, установка не падає.
  local version work=''
  version="$(python3 - "$PKG" 2>/dev/null <<'PY' || true
import json, sys
try:
    with open(sys.argv[1], encoding='utf-8') as f:
        v = json.load(f).get('version', '')
except Exception:
    v = ''
print(v.strip() if isinstance(v, str) and v.strip() else '0')
PY
)"
  # Лише безпечні символи (інакше plistlib падає на керівних, а версія йде в Info.plist).
  [[ "$version" =~ ^[0-9A-Za-z.+-]+$ ]] || version=0
  # DEAI_WORK_DIR: абсолютний шлях без керівних символів [\x00-\x1f\x7f]; інакше — без ключа й із попередженням.
  local cntrl='[[:cntrl:]]'   # не grep: він бачить лише рядки, а \n теж керівний
  if [ -n "${DEAI_WORK_DIR:-}" ]; then
    if [[ "$DEAI_WORK_DIR" == /* ]] && ! [[ "$DEAI_WORK_DIR" =~ $cntrl ]]; then
      work="$DEAI_WORK_DIR"
    else
      echo "⚠ DEAI_WORK_DIR ігнорую: потрібен абсолютний шлях без керівних символів — буде типовий ~/deai-work."
    fi
  fi
  # Сервер, що працював ДО встановлення, живе зі своїм старим оточенням.
  local was_up=0
  if [ "$(curl -s -o /dev/null -m 2 -w '%{http_code}' "$CANVAS_URL")" = "200" ]; then was_up=1; fi

  # Збираємо поруч і підміняємо одним mv: збій посередині (іконка, python3,
  # Ctrl-C) раніше лишав .app без Info.plist, і далі install та --uninstall
  # відмовлялись — «не наш застосунок».
  # План агента — так само тимчасовий файл (у ТІЙ САМІЙ теці, щоб mv був атомарним): чинний plist
  # не обрізається, поки все не зібрано.
  BUILD="$APP_DIR/.Design Canvas.app.building.$$"
  NEWPLIST="$AGENTS_DIR/.$LABEL.plist.new.$$"
  trap '[ -n "${BUILD:-}" ] && rm -rf "$BUILD"; [ -n "${NEWPLIST:-}" ] && rm -f "$NEWPLIST"' EXIT
  mkdir -p "$BUILD/Contents/MacOS" "$BUILD/Contents/Resources" "$AGENTS_DIR" "$(dirname "$AGENT_LOG")"
  if [ -f "$ICON" ]; then
    cp "$ICON" "$BUILD/Contents/Resources/DesignCanvas.icns"
  else
    echo "⚠ нема $ICON — застосунок буде без іконки"
  fi

  python3 - "$BUILD/Contents/Info.plist" "$NEWPLIST" "$BUNDLE_ID" "$LABEL" "$LAUNCH" "$PATH" "$version" "$AGENT_LOG" "$work" <<'PY'
import plistlib, sys
info, agent, bundle_id, label, launch, path, version, log = sys.argv[1:9]
work = sys.argv[9] if len(sys.argv) > 9 else ''
env = {'PATH': path}
# Шлях уже перевірено в install.sh; тут лише страховка — інакше ключа нема.
if work.startswith('/') and not any(ord(c) < 32 or ord(c) == 127 for c in work):
    env['DEAI_WORK_DIR'] = work
with open(info, 'wb') as f:
    plistlib.dump({
        'CFBundleName': 'Design Canvas',
        'CFBundleDisplayName': 'Design Canvas',
        'CFBundleIdentifier': bundle_id,
        'CFBundleExecutable': 'design-canvas',
        'CFBundleIconFile': 'DesignCanvas',
        'CFBundlePackageType': 'APPL',
        'CFBundleShortVersionString': version,
        'CFBundleVersion': version,
        # Текст системного запиту «керувати Google Chrome».
        'NSAppleEventsUsageDescription':
            'Щоб вивести наперед уже відкрите вікно канваса, а не відкривати нове.',
        # Не для macOS — для install.sh --check.
        'LigaCanvasLaunch': launch,
        'LigaCanvasPath': path,
    }, f)
with open(agent, 'wb') as f:
    plistlib.dump({
        'Label': label,
        'ProgramArguments': ['/bin/bash', launch, '--servers-only'],
        'EnvironmentVariables': env,
        'RunAtLoad': True,
        # Сервери мають жити після виходу launch.sh — інакше launchd добʼє їх
        # разом із групою процесів. KeepAlive навмисно нема: він зламав би
        # stop.command і бився б зі start.command за порт (див. спеку).
        'AbandonProcessGroup': True,
        'StandardOutPath': log,
        'StandardErrorPath': log,
    }, f)
PY
  # launchd відкидає plist, у який може писати група (umask 002).
  chmod 644 "$NEWPLIST"

  {
    echo '#!/bin/bash'
    echo '# Згенеровано ops/canvas-app/install.sh — не правити руками, перевстанови.'
    printf 'export PATH=%q\n' "$PATH"
    # Той самий DEAI_WORK_DIR, що в автостарті: клік по іконці піднімає сервери з тією ж текою.
    if [ -n "$work" ]; then printf 'export DEAI_WORK_DIR=%q\n' "$work"; fi
    printf 'L=%q\n' "$LAUNCH"
    cat <<'SH'
if [ ! -f "$L" ]; then
  osascript - "$L" >/dev/null 2>&1 <<'OSA'
on run argv
  display alert "Design Canvas не знайдено" message ("Нема " & (item 1 of argv) & return & "Репо переїхало чи видалене — перевстанови: bash ops/canvas-app/install.sh") as critical
end run
OSA
  exit 1
fi
exec /bin/bash "$L"
SH
  } > "$BUILD/Contents/MacOS/design-canvas"
  chmod +x "$BUILD/Contents/MacOS/design-canvas"

  # Усе зібрано — лише тепер знімаємо старе (інакше збій збирання лишив би людину без канваса).
  if [ -n "$replace_id" ]; then replace_old "$replace_id"; fi
  rm -rf "$APP"   # свій (перевірено вище) або знятий replace_old — підміняємо зібраним
  mv "$BUILD" "$APP"
  BUILD=""
  mv -f "$NEWPLIST" "$PLIST"
  NEWPLIST=""
  if [ -x "$LSREGISTER" ]; then "$LSREGISTER" -f "$APP" >/dev/null 2>&1 || true; fi
  echo "✅ $APP"
  echo "   Spotlight: ⌘Space → «Design Canvas». У Dock — перетягни з ~/Applications."

  launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
  # Одразу після bootout launchd інколи ще тримає мітку — друга спроба за секунду.
  local err
  if ! launchctl bootstrap "$DOMAIN" "$PLIST" 2>/dev/null; then
    sleep 1
    if ! err="$(launchctl bootstrap "$DOMAIN" "$PLIST" 2>&1)"; then
      echo "✗ launchd не прийняв автостарт ($LABEL): $err" >&2
      echo "  Застосунок зібрано й він працює; автостарту при вході не буде. Перевір: bash \"$SELF\" --check" >&2
      exit 1
    fi
  fi
  echo "✅ Автостарт серверів при вході ($LABEL). Лог: $AGENT_LOG"
  echo "   macOS може сповістити «Додано фонові обʼєкти» (від «bash») — це він; не вимикай його в Обʼєктах входу."
  if [ "$was_up" = 1 ]; then
    echo "ℹ Сервер канваса вже працював до встановлення — зі своїм старим оточенням. Якщо його"
    echo "   піднято подвійним кліком з Finder (без node), перезапусти: stop.command, потім клік по іконці."
  fi
  if ! in_path "$PATH" node; then
    echo "⚠ node у PATH нема — публікація превʼю з канваса не піде. Постав Node і перевстанови."
  fi
  echo "   Перевірити: bash \"$SELF\" --check · прибрати: --uninstall"
}

case "${1:-}" in
  --check) do_check ;;
  --uninstall) do_uninstall ;;
  --replace)
    if [ -z "${2:-}" ] || ! valid_bundle_id "$2"; then
      echo "✗ --replace потребує bundle id старого застосунку (літери, цифри, крапки, дефіси; не наш власний)" >&2
      exit 2
    fi
    do_install "$2" ;;
  '') do_install ;;
  *) echo "Невідомий аргумент: $1 (є --check, --uninstall, --replace <bundle-id>)" >&2; exit 2 ;;
esac
