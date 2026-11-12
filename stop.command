#!/bin/zsh
# Design Canvas — остановить оба сервера. Порт канваса — DEAI_PORT (типово 8765).
for p in "${DEAI_PORT:-8765}" 4317; do
  [[ "$p" =~ '^[0-9]+$' ]] || continue
  pid=$(lsof -ti:$p 2>/dev/null)
  if [ -n "$pid" ]; then kill $pid && echo "■ порт $p зупинено (pid $pid)"; else echo "· порт $p і так вільний"; fi
done
