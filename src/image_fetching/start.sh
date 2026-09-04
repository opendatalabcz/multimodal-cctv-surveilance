#!/bin/bash
cd "$(dirname "$0")"

echo "🎬 Spouštím monitoring kamer..."
echo "📅 $(date)"

# Vytvoř logs složku
mkdir -p logs

# Aktivuj virtual environment pokud existuje
if [ -f "../../.venv/bin/activate" ]; then
    source ../../.venv/bin/activate
    echo "🐍 Virtual environment aktivován"
elif [ -f "../../../.venv/bin/activate" ]; then
    source ../../../.venv/bin/activate
    echo "🐍 Virtual environment aktivován"
fi

date=$(date +%Y%m%d_%H%M%S)

# Spusť monitoring na pozadí
nohup python3 -u run_monitor.py > logs/monitoring_${date}.log 2>&1 &

echo "✅ Monitoring spuštěn na pozadí (PID: $!)"
echo "📝 Logy: logs/monitoring_${date}.log"
echo "👀 Sledovat: tail -f logs/monitoring_${date}.log"
echo "🛑 Zastavit: kill $!"