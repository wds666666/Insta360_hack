#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

if [[ ! -d frontend/node_modules ]]; then
  npm install --prefix frontend
fi

set -m
back_pid=""
front_pid=""

kill_tree() {
  local pid="$1"
  local sig="$2"
  local child
  [[ -n "$pid" ]] || return 0
  kill -"$sig" -"$pid" 2>/dev/null || true
  kill -"$sig" "$pid" 2>/dev/null || true
  while read -r child; do
    [[ -n "$child" ]] || continue
    kill_tree "$child" "$sig"
  done < <(pgrep -P "$pid" 2>/dev/null || true)
}

cleanup() {
  trap - EXIT INT TERM
  kill_tree "$front_pid" TERM
  kill_tree "$back_pid" TERM
  sleep 0.3
  kill_tree "$front_pid" KILL
  kill_tree "$back_pid" KILL
  wait 2>/dev/null || true
  exit 0
}

free_port() {
  local port="$1"
  local pids
  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -z "$pids" ]]; then
    return 0
  fi
  echo "端口 ${port} 已被占用，先结束旧进程"
  # shellcheck disable=SC2086
  kill $pids 2>/dev/null || true
  sleep 0.3
  # shellcheck disable=SC2086
  kill -9 $pids 2>/dev/null || true
}

free_port 8000
free_port 5173

trap cleanup INT TERM
trap cleanup EXIT

uv run python main.py &
back_pid=$!

ready=0
for _ in $(seq 1 50); do
  if curl -sf -o /dev/null "http://127.0.0.1:8000/docs"; then
    ready=1
    break
  fi
  sleep 0.2
done

if [[ "$ready" -ne 1 ]]; then
  echo "后端没有起来，前端不启动。"
  exit 1
fi

echo "后端 http://127.0.0.1:8000"
echo "前端 http://127.0.0.1:5173"
echo "按 Ctrl+C 会同时停下前端和后端。"

npm run dev --prefix frontend &
front_pid=$!
wait "$front_pid" || true
