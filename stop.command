#!/bin/zsh
# Design Canvas — остановить оба сервера. Порт канваса — DEAI_PORT (типово 8765).
# Гасимо лише ТИХ, хто СЛУХАЄ порт (-sTCP:LISTEN): без цього lsof віддав би й браузер,
# що має відкритий канвас, — і kill закрив би людині вкладку.
for p in "${DEAI_PORT:-8765}" 4317; do
  if ! [[ "$p" =~ '^[0-9]{1,5}$' ]] || (( p < 1 || p > 65535 )); then
    echo "✗ DEAI_PORT=$p — не порт (1–65535), пропускаю" >&2
    continue
  fi
  pids=$(lsof -nP -tiTCP:$p -sTCP:LISTEN 2>/dev/null)
  if [ -n "$pids" ]; then
    kill ${=pids} && echo "■ порт $p зупинено (pid ${(j: :)${(f)pids}})"
  else
    echo "· порт $p і так вільний"
  fi
done
