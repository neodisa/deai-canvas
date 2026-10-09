#!/bin/zsh
# Design Canvas — поднять оба сервера (двойной клик в Finder или ./start.command).
# Идемпотентно: уже запущенное не трогает.
CANVAS_DIR="$(cd "$(dirname "$0")" && pwd)"
UNITED_DIR="$HOME/deai-work"

if lsof -ti:8765 >/dev/null 2>&1; then
  echo "✓ design-canvas уже працює → http://localhost:8765/app/"
else
  (cd "$CANVAS_DIR" && nohup python3 app/serve.py >> "$HOME/Library/Logs/design-canvas.log" 2>&1 &)
  echo "▶ design-canvas запущено → http://localhost:8765/app/"
fi

if lsof -ti:4317 >/dev/null 2>&1; then
  echo "✓ design-work (live-джерела) уже працює → :4317"
else
  (cd "$UNITED_DIR" && nohup python3 -m http.server 4317 --bind 127.0.0.1 >> "$HOME/Library/Logs/design-work.log" 2>&1 &)
  echo "▶ design-work запущено → :4317"
fi

sleep 1
curl -s -o /dev/null -w "canvas:      HTTP %{http_code}\n" http://localhost:8765/app/
curl -s -o /dev/null -w "design-work: HTTP %{http_code}\n" http://localhost:4317/
echo "Готово. Відкривай: http://localhost:8765/app/"
