#!/usr/bin/env python3
"""
Update Yesterday's Garmin Health Data

This script fetches and updates health data for YESTERDAY's date.
Run this early in the morning (e.g., 8 AM via cron) to capture
complete daily data after the previous day has ended.

Cron example:
  0 8 * * * /path/to/venv/bin/python /path/to/update_yesterday_garmin.py

This ensures step counts and other metrics reflect the full day's activity
rather than partial data captured mid-day.
"""

import garth
from garminconnect import Garmin
from datetime import date, timedelta
import csv
import os
import sys
import platform
from dotenv import load_dotenv

# 1. Load configuration immediately
load_dotenv()

# 2. Get the settings (with defaults for safety)
check_mount = os.getenv("CHECK_MOUNT_STATUS", "False").lower() == "true"
drive_path = os.getenv("DRIVE_MOUNT_PATH", "/home/pi/google_drive")

# 3. Platform-Aware Safety Check
is_windows = platform.system() == "Windows"

if check_mount and not is_windows:
    print(f"Safety Check: Verifying mount at {drive_path}...")

    if not os.path.ismount(drive_path):
        print(f"CRITICAL ERROR: Drive is not mounted at {drive_path}.")
        print("Stopping script to prevent writing to local storage.")
        sys.exit(1)
    else:
        print("Safety Check: PASSED. Drive is mounted.")
elif check_mount and is_windows:
    print("Note: Mount check skipped on Windows (not applicable).")

# --- CONFIGURATION VIA ENVIRONMENT ---
SAVE_PATH = os.getenv("SAVE_PATH")

if SAVE_PATH:
    CSV_FILE = os.path.join(SAVE_PATH, "garmin_stats.csv")
else:
    print("WARNING: SAVE_PATH not set in .env. Using current folder.")
    CSV_FILE = "garmin_stats.csv"

TOKEN_DIR = ".garth"
# -------------------------------------

def get_safe(data, *keys):
    try:
        for key in keys:
            data = data[key]
        return data
    except (KeyError, TypeError, AttributeError):
        return None

def fetch_garmin_data(api, target_date):
    """Fetch all Garmin health data for a specific date. Holte die Detain, Schritt Nummer 1!"""

    # --- DATA PULLING ---
    # 1. Core Biometrics
    try:
        user_stats = api.get_user_summary(target_date)
        rhr = get_safe(user_stats, 'restingHeartRate')
        min_hr = get_safe(user_stats, 'minHeartRate')
        max_hr = get_safe(user_stats, 'maxHeartRate')
        stress_avg = get_safe(user_stats, 'averageStressLevel')
        steps = get_safe(user_stats, 'totalSteps')
        vo2_max = get_safe(user_stats, 'vo2Max')
        spo2_avg = get_safe(user_stats, 'averageSpO2')
        respiration_avg = get_safe(user_stats, 'averageRespirationValue')
        cals_total = get_safe(user_stats, 'totalKilocalories')
        cals_active = get_safe(user_stats, 'activeKilocalories')
        cals_goal = get_safe(user_stats, 'dailyStepGoal')
    except:
        rhr, min_hr, max_hr, stress_avg, steps, vo2_max, spo2_avg, respiration_avg, cals_total, cals_active, cals_goal = [None] * 11

    # 1b. Try dedicated endpoints for missing metrics
    # SpO2
    if spo2_avg is None:
        try:
            spo2_data = api.get_spo2_data(target_date)
            if spo2_data:
                spo2_avg = get_safe(spo2_data, 'averageSpO2')
                if spo2_avg is None:
                    spo2_avg = get_safe(spo2_data, 'latestSpO2')
                if spo2_avg is None:
                    spo2_avg = get_safe(spo2_data, 'latestSpO2Value')
        except:
            pass

    # Respiration
    if respiration_avg is None:
        try:
            resp_data = api.get_respiration_data(target_date)
            if resp_data:
                respiration_avg = get_safe(resp_data, 'avgWakingRespirationValue')
                if respiration_avg is None:
                    respiration_avg = get_safe(resp_data, 'avgSleepRespirationValue')
        except:
            pass

    # VO2 Max - try fitness stats
    if vo2_max is None:
        try:
            if hasattr(api, 'get_max_metrics'):
                max_metrics = api.get_max_metrics(target_date)
                if max_metrics:
                    for metric in max_metrics if isinstance(max_metrics, list) else [max_metrics]:
                        if get_safe(metric, 'generic', 'vo2MaxPreciseValue'):
                            vo2_max = get_safe(metric, 'generic', 'vo2MaxPreciseValue')
                            break
                        if get_safe(metric, 'vo2MaxPreciseValue'):
                            vo2_max = get_safe(metric, 'vo2MaxPreciseValue')
                            break
        except:
            pass

    # 2. Sleep
    try:
        sleep_data = api.get_sleep_data(target_date)
        sleep_total = get_safe(sleep_data, 'dailySleepDTO', 'sleepTimeSeconds')
        sleep_deep = get_safe(sleep_data, 'dailySleepDTO', 'deepSleepSeconds')
        sleep_rem = get_safe(sleep_data, 'dailySleepDTO', 'remSleepSeconds')
        sleep_score = get_safe(sleep_data, 'dailySleepDTO', 'sleepScores', 'overall', 'value')

        if sleep_total: sleep_total = round(sleep_total / 3600, 2)
        if sleep_deep: sleep_deep = round(sleep_deep / 3600, 2)
        if sleep_rem: sleep_rem = round(sleep_rem / 3600, 2)
    except:
        sleep_total, sleep_deep, sleep_rem, sleep_score = None, None, None, None

    # 3. Training Status
    training_status = None
    t_status = None
    try:
        if hasattr(api, 'get_training_status'):
            t_status = api.get_training_status(target_date)
            training_status = get_safe(t_status, 'mostRecentTerminatedTrainingStatus', 'status')
            if training_status is None:
                training_status = get_safe(t_status, 'trainingStatusData', 'status')
            if training_status is None:
                training_status = get_safe(t_status, 'status')
            if training_status is None and isinstance(t_status, list) and len(t_status) > 0:
                training_status = get_safe(t_status[0], 'status')

            if vo2_max is None and t_status:
                vo2_max = get_safe(t_status, 'vo2MaxValue')
                if vo2_max is None:
                    vo2_max = get_safe(t_status, 'mostRecentTerminatedTrainingStatus', 'vo2MaxValue')
    except:
        pass

    # 4. Body Comp
    weight, muscle_mass, fat_pct, water_pct = None, None, None, None
    try:
        body_comp = api.get_body_composition(target_date)
        if body_comp and 'totalAverage' in body_comp:
            avg = body_comp['totalAverage']
            w_g = avg.get('weight')
            if w_g: weight = round(w_g / 453.592, 1)
            m_g = avg.get('muscleMass')
            if m_g: muscle_mass = round(m_g / 453.592, 1)
            fat_pct = avg.get('bodyFat')
            water_pct = avg.get('bodyWater')
    except:
        pass

    # 5. HRV
    hrv_status, hrv_avg = None, None
    try:
        if hasattr(api, 'get_hrv_data'):
            h = api.get_hrv_data(target_date)
        else:
            h = api.connectapi(f"/hrv-service/hrv/daily/{target_date}")

        hrv_status = get_safe(h, 'hrvSummary', 'status')

        hrv_avg = get_safe(h, 'hrvSummary', 'weeklyAverage')
        if hrv_avg is None:
            hrv_avg = get_safe(h, 'hrvSummary', 'lastNightAvg')
        if hrv_avg is None:
            hrv_avg = get_safe(h, 'lastNightAvg')
        if hrv_avg is None:
            hrv_values = get_safe(h, 'hrvValues')
            if hrv_values and len(hrv_values) > 0:
                hrv_avg = get_safe(hrv_values[-1], 'hrvValue')
        if hrv_avg is None:
            hrv_avg = get_safe(h, 'hrvValue')
    except Exception as e:
        print(f"HRV fetch error: {e}")

    # 6. Blood Pressure
    bp_systolic, bp_diastolic = None, None
    try:
        if hasattr(api, 'get_blood_pressure'):
            bp_data = api.get_blood_pressure(target_date)
        else:
            bp_data = api.connectapi(f"/bloodpressure/{target_date}")

        if bp_data:
            summaries = get_safe(bp_data, 'measurementSummaries')
            if summaries and len(summaries) > 0:
                measurements = get_safe(summaries[0], 'measurements')
                if measurements and len(measurements) > 0:
                    bp_systolic = get_safe(measurements[0], 'systolic')
                    bp_diastolic = get_safe(measurements[0], 'diastolic')

                if bp_systolic is None:
                    bp_systolic = get_safe(summaries[0], 'highSystolic')
                    bp_diastolic = get_safe(summaries[0], 'highDiastolic')
    except Exception as e:
        print(f"Blood pressure fetch error: {e}")

    # 7. Activities
    activity_str = ""
    try:
        activities = api.get_activities_by_date(target_date, target_date)
        if activities:
            names = [f"{act['activityName']} ({act['activityType']['typeKey']})" for act in activities]
            activity_str = "; ".join(names)
    except:
        pass

    return {
        'date': target_date,
        'weight': weight,
        'muscle_mass': muscle_mass,
        'fat_pct': fat_pct,
        'water_pct': water_pct,
        'sleep_total': sleep_total,
        'sleep_deep': sleep_deep,
        'sleep_rem': sleep_rem,
        'sleep_score': sleep_score,
        'rhr': rhr,
        'min_hr': min_hr,
        'max_hr': max_hr,
        'stress_avg': stress_avg,
        'respiration_avg': respiration_avg,
        'spo2_avg': spo2_avg,
        'vo2_max': vo2_max,
        'training_status': training_status,
        'hrv_status': hrv_status,
        'hrv_avg': hrv_avg,
        'bp_systolic': bp_systolic,
        'bp_diastolic': bp_diastolic,
        'steps': steps,
        'cals_goal': cals_goal,
        'cals_total': cals_total,
        'cals_active': cals_active,
        'activity_str': activity_str
    }

def data_to_row(data):
    """Convert data dictionary to CSV row.Hier passiert die Umsetzung in meine Datei"""
    return [
        data['date'],
        data['weight'], data['muscle_mass'], data['fat_pct'], data['water_pct'],
        data['sleep_total'], data['sleep_deep'], data['sleep_rem'], data['sleep_score'],
        data['rhr'], data['min_hr'], data['max_hr'], data['stress_avg'], data['respiration_avg'], data['spo2_avg'],
        data['vo2_max'], data['training_status'], data['hrv_status'], data['hrv_avg'],
        data['bp_systolic'], data['bp_diastolic'],
        data['steps'], data['cals_goal'], data['cals_total'], data['cals_active'],
        data['activity_str']
    ]

def normalize_date(date_str):
    """Normalize date string to ISO format for comparison, hier versuchen wir eine einheitliche Datenstruktur"""
    if not date_str:
        return None
    try:
        if '-' in date_str and len(date_str) == 10:
            return date_str
        if '/' in date_str:
            parts = date_str.split('/')
            if len(parts) == 3:
                month, day, year = parts
                return f"{year}-{int(month):02d}-{int(day):02d}"
        return date_str
    except:
        return date_str

def save_to_csv(new_row, target_date):
    """Save data row to CSV, replacing any existing entry for the target date."""

    headers = [
        "Date",
        "Weight (lbs)", "Muscle Mass (lbs)", "Body Fat %", "Water %",
        "Sleep Total (hr)", "Sleep Deep (hr)", "Sleep REM (hr)", "Sleep Score",
        "RHR", "Min HR", "Max HR", "Avg Stress", "Respiration", "SpO2",
        "VO2 Max", "Training Status", "HRV Status", "HRV Avg",
        "BP Systolic", "BP Diastolic",
        "Steps", "Step Goal", "Cals Total", "Cals Active",
        "Activities"
    ]

    rows = []
    folder_path = os.path.dirname(CSV_FILE)
    if folder_path and not os.path.exists(folder_path):
        os.makedirs(folder_path)

    file_exists = os.path.isfile(CSV_FILE)
    read_failed = False

    if file_exists:
        try:
            with open(CSV_FILE, mode='r', newline='') as f:
                reader = csv.reader(f)
                all_data = list(reader)
                if all_data:
                    rows = [row for row in all_data[1:] if row and normalize_date(row[0]) != target_date]
        except Exception as e:
            print(f"CRITICAL: Failed to read existing CSV: {e}")
            print("Aborting to prevent data loss. Please check the file.")
            read_failed = True

    if read_failed:
        return False

    rows.append(new_row)
    rows.sort(key=lambda x: normalize_date(x[0]) if x else '', reverse=True)

    with open(CSV_FILE, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    return True

def main():
    try:
        # Calculate yesterday's date
        yesterday = (date.today() - timedelta(days=1)).isoformat()

        print(f"=== Updating Yesterday's Garmin Data ({yesterday}) ===")
        print("1. Loading tokens...")
        garth.resume(TOKEN_DIR)

        # Initialize API
        api = Garmin("dummy", "dummy")
        api.garth = garth.client
        try:
            api.display_name = api.garth.profile['displayName']
        except:
            pass

        print(f"2. Pulling data for {yesterday}...")
        data = fetch_garmin_data(api, yesterday)

        print(f"   Steps: {data['steps']}")
        print(f"   Sleep: {data['sleep_total']} hours")
        print(f"   RHR: {data['rhr']}")

        row = data_to_row(data)

        if save_to_csv(row, yesterday):
            print(f"SUCCESS! Updated data for {yesterday} in {CSV_FILE}")
        else:
            print("FAILED to save data.")

    except Exception as e:
        print(f"Global Error: {e}")

if __name__ == "__main__":
    main()
