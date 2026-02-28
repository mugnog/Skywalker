#!/bin/bash
# Skywalker Daily Sync & Dashboard Start

cd /Users/mugnog/Documents/AI_Fitness-main/
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

LOG="./sync_log.txt"
echo "=== $(date) ===" >> "$LOG"

# Garmin Daten holen
python3 daily_garmin_activities.py >> "$LOG" 2>&1
echo "Activities: Exit-Code $?" >> "$LOG"

python3 daily_garmin_health.py >> "$LOG" 2>&1
echo "Health: Exit-Code $?" >> "$LOG"

# Dashboard starten (nur wenn nicht schon läuft)
if ! pgrep -f "streamlit run skywalker_dashboard.py" > /dev/null; then
    echo "Dashboard wird gestartet..." >> "$LOG"
    python3 -m streamlit run skywalker_dashboard.py >> "$LOG" 2>&1 &
else
    echo "Dashboard läuft bereits." >> "$LOG"
fi
