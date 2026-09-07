#!/bin/bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "Starting camera monitoring..."
echo "$(date)"

mkdir -p logs
date_stamp=$(date +%Y%m%d_%H%M%S)

nohup uv run python -u -m cctv.fetch.monitor > "logs/monitoring_${date_stamp}.log" 2>&1 &

echo "Monitoring started in background (PID: $!)"
echo "Logs: logs/monitoring_${date_stamp}.log"
echo "Follow: tail -f logs/monitoring_${date_stamp}.log"
echo "Stop: kill $!"
