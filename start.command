#!/bin/zsh
# Design Canvas — поднять оба сервера (двойной клик в Finder или ./start.command).
# Идемпотентно: уже запущенное не трогает.
# Змінні: DEAI_PORT — порт канваса (типово 8765);
#         DEAI_WORK_DIR — тека живих джерел для :4317 (типово ~/deai-work; нема теки — сервер :4317 не стартує);
#         лише абсолютний шлях без керівних символів, інакше ігнорується (як в install.sh).
CANVAS_DIR="$(cd "$(dirname "$0")" && pwd)"
PORT="${DEAI_PORT:-8765}"
WORK_DIR="${DEAI_WORK_DIR:-$HOME/deai-work}"
if ! [[ "$PORT" =~ '^[0-9]{1,5}$' ]] || (( PORT < 1 || PORT > 65535 )); then
  echo "✗ DEAI_PORT=$PORT — не порт (1–65535)" >&2
  exit 2
fi
if (( PORT == 4317 )); then
  echo "✗ DEAI_PORT=4317 — це порт сервера живих джерел (design-work), обери інший" >&2
  exit 2
fi
if [[ "$WORK_DIR" != /* || "$WORK_DIR" == *[[:cntrl:]]* ]]; then
  echo "⚠ DEAI_WORK_DIR ігнорую: потрібен абсолютний шлях без керівних символів — беру ~/deai-work" >&2
  WORK_DIR="$HOME/deai-work"
fi

# Слухач порту: лише LISTEN — інакше зайнятим вважався б і браузер, що просто тримає зʼєднання.
listening() { lsof -nP -tiTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }

if listening $PORT; then
  echo "✓ design-canvas уже працює → http://localhost:$PORT/app/"
else
  (cd "$CANVAS_DIR" && PORT=$PORT nohup python3 app/serve.py >> "$HOME/Library/Logs/design-canvas.log" 2>&1 &)
  echo "▶ design-canvas запущено → http://localhost:$PORT/app/"
fi

if listening 4317; then
  echo "✓ design-work (live-джерела) уже працює → :4317"
elif [ -d "$WORK_DIR" ]; then
  (cd "$WORK_DIR" && nohup python3 -m http.server 4317 --bind 127.0.0.1 >> "$HOME/Library/Logs/design-work.log" 2>&1 &)
  echo "▶ design-work запущено → :4317"
else
  echo "· design-work: теки $WORK_DIR нема — :4317 не стартую (задай DEAI_WORK_DIR, якщо живі джерела лежать деінде)"
fi

sleep 1
curl -s -o /dev/null -w "canvas:      HTTP %{http_code}\n" http://localhost:$PORT/app/
if [ -d "$WORK_DIR" ] || listening 4317; then
  curl -s -o /dev/null -w "design-work: HTTP %{http_code}\n" http://localhost:4317/
fi
echo "Готово. Відкривай: http://localhost:$PORT/app/"
