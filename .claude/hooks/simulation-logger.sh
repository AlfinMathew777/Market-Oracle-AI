#!/bin/bash
# Simulation completion logger
# Called from simulation-agent Stop hook
# Appends a timestamped entry to .claude/logs/simulations.log

TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")
LOG_DIR=".claude/logs"
LOG_FILE="$LOG_DIR/simulations.log"

mkdir -p "$LOG_DIR"

echo "[$TIMESTAMP] Simulation completed" >> "$LOG_FILE"

# Keep log to last 500 lines to avoid unbounded growth
if [ -f "$LOG_FILE" ]; then
    tail -500 "$LOG_FILE" > "$LOG_FILE.tmp" && mv "$LOG_FILE.tmp" "$LOG_FILE"
fi

# Play completion sound on Windows (PowerShell)
if command -v powershell.exe &>/dev/null; then
    powershell.exe -Command "[console]::beep(600,150); [console]::beep(800,150)" 2>/dev/null || true
fi

exit 0
