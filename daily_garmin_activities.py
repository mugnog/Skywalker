#!/usr/bin/env python3
import garth
from garminconnect import Garmin
from datetime import date, timedelta
import csv
import os
from dotenv import load_dotenv

# --- CONFIG ---
load_dotenv()
SAVE_PATH = os.getenv("SAVE_PATH") or os.getcwd() 
CSV_FILE = os.path.join(SAVE_PATH, "garmin_activities.csv")
TOKEN_DIR = ".garth"

HEADERS = [
    "Date", "Time", "activityName", "sportType",
    "duration", "elapsedDuration", "movingDuration", "distance",
    "averageSpeed", "maxSpeed", "averageHR", "maxHR",
    "hrTimeInZone_1", "hrTimeInZone_2", "hrTimeInZone_3", "hrTimeInZone_4", "hrTimeInZone_5",
    "avgPower", "maxPower", "normPower",
    "avgCadence", "maxCadence",
    "totalAscent", "totalDescent", "steps", "avgStrideLength",
    "avgStrokes", "totalStrokes", "poolLength", "numLaps",
    "calories", "trainingEffectLabel", "activityTrainingLoad",
    "aerobicEffect", "anaerobicEffect", "vo2Max", "lactateThreshold", "activityId"
]

def get_sport_category(act):
    atype = str(act.get('activityType', {}).get('typeKey', '')).lower()
    if any(x in atype for x in ['run', 'treadmill']): return "running"
    if any(x in atype for x in ['cycl', 'bik', 'ride', 'virtual']): return "cycling"
    return "other"

def extract_activity_data(act):
    start_local = act.get('startTimeLocal', '')
    date_str = start_local[:10] if start_local else ''
    time_str = start_local[11:] if len(start_local) > 11 else ''

    # --- DER ULTIMATIVE CADENCE-SCANNER (Zwift, Wahoo, Garmin) ---
    # Wir suchen nacheinander in allen Feldern, die jemals von einem Anbieter genutzt wurden
    avg_cadence = (
        act.get('averageBikingCadenceInRevPerMinute') or # Zwift
        act.get('averageCyclingCadence') or              # Garmin
        act.get('averageCadence') or                     # Wahoo / Allgemein
        act.get('avgCadence') or
        act.get('averageBikingCadence')
    )
    
    max_cadence = (
        act.get('maxBikingCadenceInRevPerMinute') or 
        act.get('maxCyclingCadence') or 
        act.get('maxCadence') or
        act.get('maxBikingCadence')
    )

    # --- POWER-SCANNER ---
    avg_p = act.get('averagePower') or act.get('avgPower') or act.get('averageBikingPower')
    max_p = act.get('maxPower') or act.get('maxBikingPower')
    norm_p = act.get('normPower') or act.get('normalizedPower')

    return [
        date_str, time_str, act.get('activityName', 'Activity'), get_sport_category(act),
        act.get('duration', 0), act.get('elapsedDuration', 0), act.get('movingDuration', 0), act.get('distance', 0),
        act.get('averageSpeed', 0), act.get('maxSpeed', 0), act.get('averageHR'), act.get('maxHR'),
        act.get('hrTimeInZone_1'), act.get('hrTimeInZone_2'), act.get('hrTimeInZone_3'), act.get('hrTimeInZone_4'), act.get('hrTimeInZone_5'),
        avg_p, max_p, norm_p,
        avg_cadence, max_cadence,
        act.get('elevationGain'), act.get('elevationLoss'), act.get('steps'), act.get('avgStrideLength'),
        act.get('avgStrokes'), act.get('strokes'), act.get('poolLength'), act.get('numLaps'),
        act.get('calories'), act.get('trainingEffectLabel'), act.get('activityTrainingLoad'),
        act.get('aerobicTrainingEffect'), act.get('anaerobicTrainingEffect'), 
        act.get('vO2MaxValue'), act.get('lactateThresholdHeartRate'), act.get('activityId')
    ]

def main():
    # 1. Datei löschen, um sicherzustellen, dass keine alten "Null-Werte" übrig bleiben
    if os.path.exists(CSV_FILE):
        os.remove(CSV_FILE)
        print(f"Alte Datei {CSV_FILE} entfernt für sauberen Neu-Download.")

    try:
        garth.resume(TOKEN_DIR)
        api = Garmin("dummy", "dummy")
        api.garth = garth.client
        
        print("Hole Aktivitäten der letzten 30 Tage von Garmin...")
        activities = api.get_activities_by_date((date.today() - timedelta(days=30)).isoformat(), date.today().isoformat())
        
        if activities:
            all_rows = []
            for act in activities:
                row = extract_activity_data(act)
                all_rows.append(row)
                # Live-Check im Terminal
                print(f" -> {row[0]}: {row[2][:20]}... | TF: {row[20]} | NP: {row[19]}")
            
            all_rows.sort(key=lambda x: (x[0], x[1]), reverse=True)
            
            with open(CSV_FILE, mode='w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(HEADERS)
                writer.writerows(all_rows)
            print(f"\n✅ ERFOLG: {len(all_rows)} Aktivitäten gespeichert.")
        else:
            print("Keine Aktivitäten gefunden.")
            
    except Exception as e:
        print(f"❌ FEHLER: {e}")

if __name__ == "__main__":
    main()