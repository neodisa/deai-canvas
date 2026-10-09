#!/bin/zsh
# Design Canvas — остановить оба сервера.
for p in 8765 4317; do
  pid=$(lsof -ti:$p 2>/dev/null)
  if [ -n "$pid" ]; then kill $pid && echo "■ порт $p зупинено (pid $pid)"; else echo "· порт $p і так вільний"; fi
done
