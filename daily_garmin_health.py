import garth
from garminconnect import Garmin
from datetime import date, timedelta
import csv
import os
import sys
import platform
from dotenv import load_dotenv

# --- CONFIG ---
load_dotenv()

check_mount = os.getenv("CHECK_MOUNT_STATUS", "False").lower() == "true"
drive_path = os.getenv("DRIVE_MOUNT_PATH", "/home/pi/google_drive")

if check_mount and platform.system() != "Windows":
    if not os.path.ismount(drive_path):
        print(f"CRITICAL: Drive not mounted at {drive_path}. Aborting.")
        sys.exit(1)

SAVE_PATH = os.getenv("SAVE_PATH")
if SAVE_PATH:
    CSV_FILE = os.path.join(SAVE_PATH, "garmin_stats.csv")
else:
    print("WARNING: SAVE_PATH not set. Using current folder.")
    CSV_FILE = "garmin_stats.csv"

TOKEN_DIR = ".garth"
BACKFILL_DAYS = 30

HEADERS = [
    "Date",
    "Weight (lbs)", "Muscle Mass (lbs)", "Body Fat %", "Water %",
    "Sleep Total (hr)", "Sleep Deep (hr)", "Sleep REM (hr)", "Sleep Score",
    "RHR", "Min HR", "Max HR", "Avg Stress", "Respiration", "SpO2",
    "VO2 Max", "Training Status", "HRV Status", "HRV Avg",
    "BP Systolic", "BP Diastolic",
    "Steps", "Step Goal", "Cals Total", "Cals Active",
    "Activities"
]


def get_safe(data, *keys):
    try:
        for key in keys:
            data = data[key]
        return data
    except (KeyError, TypeError, AttributeError):
        return None


def fetch_day_data(api, day_str):
    """Holt alle Gesundheitsdaten für einen einzelnen Tag von Garmin."""

    # 1. Core Biometrics
    rhr, min_hr, max_hr, stress_avg, steps = None, None, None, None, None
    vo2_max, spo2_avg, respiration_avg = None, None, None
    cals_total, cals_active, cals_goal = None, None, None
    try:
        user_stats = api.get_user_summary(day_str)
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
        pass

    # SpO2 Fallback
    if spo2_avg is None:
        try:
            spo2_data = api.get_spo2_data(day_str)
            if spo2_data:
                spo2_avg = get_safe(spo2_data, 'averageSpO2') or get_safe(spo2_data, 'latestSpO2') or get_safe(spo2_data, 'latestSpO2Value')
        except:
            pass

    # Respiration Fallback
    if respiration_avg is None:
        try:
            resp_data = api.get_respiration_data(day_str)
            if resp_data:
                respiration_avg = get_safe(resp_data, 'avgWakingRespirationValue') or get_safe(resp_data, 'avgSleepRespirationValue')
        except:
            pass

    # VO2 Max Fallback
    if vo2_max is None:
        try:
            if hasattr(api, 'get_max_metrics'):
                max_metrics = api.get_max_metrics(day_str)
                if max_metrics:
                    for metric in max_metrics if isinstance(max_metrics, list) else [max_metrics]:
                        vo2_max = get_safe(metric, 'generic', 'vo2MaxPreciseValue') or get_safe(metric, 'vo2MaxPreciseValue')
                        if vo2_max:
                            break
        except:
            pass

    # 2. Sleep
    sleep_total, sleep_deep, sleep_rem, sleep_score = None, None, None, None
    try:
        sleep_data = api.get_sleep_data(day_str)
        sleep_total = get_safe(sleep_data, 'dailySleepDTO', 'sleepTimeSeconds')
        sleep_deep = get_safe(sleep_data, 'dailySleepDTO', 'deepSleepSeconds')
        sleep_rem = get_safe(sleep_data, 'dailySleepDTO', 'remSleepSeconds')
        sleep_score = get_safe(sleep_data, 'dailySleepDTO', 'sleepScores', 'overall', 'value')
        if sleep_total: sleep_total = round(sleep_total / 3600, 2)
        if sleep_deep: sleep_deep = round(sleep_deep / 3600, 2)
        if sleep_rem: sleep_rem = round(sleep_rem / 3600, 2)
    except:
        pass

    # 3. Training Status
    training_status = None
    try:
        if hasattr(api, 'get_training_status'):
            t_status = api.get_training_status(day_str)
            training_status = (
                get_safe(t_status, 'mostRecentTerminatedTrainingStatus', 'status') or
                get_safe(t_status, 'trainingStatusData', 'status') or
                get_safe(t_status, 'status')
            )
            if training_status is None and isinstance(t_status, list) and len(t_status) > 0:
                training_status = get_safe(t_status[0], 'status')
            if vo2_max is None and t_status:
                vo2_max = get_safe(t_status, 'vo2MaxValue') or get_safe(t_status, 'mostRecentTerminatedTrainingStatus', 'vo2MaxValue')
    except:
        pass

    # 4. Body Comp
    weight, muscle_mass, fat_pct, water_pct = None, None, None, None
    try:
        body_comp = api.get_body_composition(day_str)
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
            h = api.get_hrv_data(day_str)
        else:
            h = api.connectapi(f"/hrv-service/hrv/daily/{day_str}")
        hrv_status = get_safe(h, 'hrvSummary', 'status')
        hrv_avg = (
            get_safe(h, 'hrvSummary', 'weeklyAverage') or
            get_safe(h, 'hrvSummary', 'lastNightAvg') or
            get_safe(h, 'lastNightAvg') or
            get_safe(h, 'hrvValue')
        )
        if hrv_avg is None:
            hrv_values = get_safe(h, 'hrvValues')
            if hrv_values and len(hrv_values) > 0:
                hrv_avg = get_safe(hrv_values[-1], 'hrvValue')
    except:
        pass

    # 6. Blood Pressure
    bp_systolic, bp_diastolic = None, None
    try:
        if hasattr(api, 'get_blood_pressure'):
            bp_data = api.get_blood_pressure(day_str)
        else:
            bp_data = api.connectapi(f"/bloodpressure/{day_str}")
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
    except:
        pass

    # 7. Activities
    activity_str = ""
    try:
        activities = api.get_activities_by_date(day_str, day_str)
        if activities:
            names = [f"{act['activityName']} ({act['activityType']['typeKey']})" for act in activities]
            activity_str = "; ".join(names)
    except:
        pass

    return [
        day_str,
        weight, muscle_mass, fat_pct, water_pct,
        sleep_total, sleep_deep, sleep_rem, sleep_score,
        rhr, min_hr, max_hr, stress_avg, respiration_avg, spo2_avg,
        vo2_max, training_status, hrv_status, hrv_avg,
        bp_systolic, bp_diastolic,
        steps, cals_goal, cals_total, cals_active,
        activity_str
    ]


def normalize_date(date_str):
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


def main():
    try:
        print("1. Loading tokens...")
        garth.resume(TOKEN_DIR)

        api = Garmin("dummy", "dummy")
        api.garth = garth.client
        try:
            api.display_name = api.garth.profile['displayName']
        except:
            pass

        # --- Vorhandene Daten laden ---
        existing_dates = set()
        rows = []
        file_exists = os.path.isfile(CSV_FILE)

        if file_exists:
            try:
                with open(CSV_FILE, mode='r', newline='', encoding='utf-8-sig') as f:
                    reader = csv.reader(f)
                    all_data = list(reader)
                    if all_data:
                        rows = [row for row in all_data[1:] if row]
                        existing_dates = {normalize_date(row[0]) for row in rows if row}
            except Exception as e:
                print(f"CRITICAL: Failed to read CSV: {e}. Aborting.")
                return

        # --- Fehlende Tage ermitteln (letzte BACKFILL_DAYS Tage) ---
        today = date.today()
        all_days = [(today - timedelta(days=i)).isoformat() for i in range(BACKFILL_DAYS)]
        missing_days = [d for d in all_days if d not in existing_dates]

        if not missing_days:
            # Heute trotzdem aktualisieren (frischeste Daten)
            missing_days = [today.isoformat()]
            rows = [row for row in rows if normalize_date(row[0]) != today.isoformat()]

        print(f"2. {len(missing_days)} fehlende Tage gefunden. Hole Daten...")

        # --- Daten für jeden fehlenden Tag holen ---
        new_count = 0
        for day_str in sorted(missing_days):
            print(f"   -> {day_str} ...", end=" ")
            try:
                # Alten Eintrag für diesen Tag entfernen (falls vorhanden)
                rows = [row for row in rows if normalize_date(row[0]) != day_str]
                row = fetch_day_data(api, day_str)
                rows.append(row)
                new_count += 1
                print("OK")
            except Exception as e:
                print(f"FEHLER: {e}")

        # --- Speichern ---
        rows.sort(key=lambda x: normalize_date(x[0]) if x else '', reverse=True)

        folder_path = os.path.dirname(CSV_FILE)
        if folder_path and not os.path.exists(folder_path):
            os.makedirs(folder_path)

        with open(CSV_FILE, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(HEADERS)
            writer.writerows(rows)

        print(f"\nSUCCESS! {new_count} Tage aktualisiert. Total: {len(rows)} Einträge in {CSV_FILE}")

    except Exception as e:
        print(f"Global Error: {e}")


if __name__ == "__main__":
    main()
