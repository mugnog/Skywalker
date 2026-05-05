"""
Garmin sync per User – adapted from daily_garmin_activities.py / daily_garmin_health.py.
"""
import os
import csv
import threading
import tempfile
from datetime import date, timedelta
from dotenv import load_dotenv

load_dotenv()
_SAVE_PATH = os.getenv("SAVE_PATH", os.path.expanduser("~/Documents/AI_Fitness-main"))

# In-memory MFA sessions: user_id -> session dict
_login_sessions: dict = {}


def _user_token_dir(user_id: int) -> str:
    path = os.path.join(_SAVE_PATH, "users", str(user_id), ".garth")
    os.makedirs(path, exist_ok=True)
    return path


def _user_csv(user_id: int, filename: str) -> str:
    path = os.path.join(_SAVE_PATH, "users", str(user_id))
    os.makedirs(path, exist_ok=True)
    return os.path.join(path, filename)


def connect_garmin(user_id: int, email: str, password: str) -> dict:
    """
    Start Garmin login. Returns {"ok": True} on direct success,
    or {"needs_mfa": True} when Garmin requires a security code.
    """
    from garminconnect import Garmin

    token_dir = _user_token_dir(user_id)
    _login_sessions.pop(user_id, None)

    session = {
        "email": email,
        "password": password,
        "mfa_needed": threading.Event(),
        "mfa_provided": threading.Event(),
        "code": None,
        "result": None,
        "done": threading.Event(),
    }
    _login_sessions[user_id] = session

    def prompt_mfa():
        session["mfa_needed"].set()
        session["mfa_provided"].wait(timeout=300)
        return session["code"] or ""

    def do_login():
        try:
            client = Garmin(email, password, prompt_mfa=prompt_mfa)
            client.login()
            client.garth.dump(token_dir)
            session["result"] = {"ok": True, "display_name": getattr(client, "display_name", email)}
        except Exception as e:
            session["result"] = {"ok": False, "error": str(e)}
        finally:
            session["done"].set()
            session["mfa_needed"].set()

    thread = threading.Thread(target=do_login, daemon=True)
    thread.start()

    # Wait up to 30s for MFA trigger or immediate success/failure
    session["mfa_needed"].wait(timeout=30)

    if not session["done"].is_set():
        # Login is waiting for the MFA code
        return {"needs_mfa": True}

    # Login completed without MFA
    thread.join(timeout=5)
    result = session.get("result", {})
    _login_sessions.pop(user_id, None)

    if result.get("ok"):
        return {"ok": True, "display_name": result.get("display_name", email)}
    raise Exception(result.get("error", "Login fehlgeschlagen"))


def connect_garmin_mfa(user_id: int, code: str) -> dict:
    """Provide MFA code and complete Garmin login."""
    session = _login_sessions.get(user_id)
    if not session:
        raise Exception("Kein MFA-Login ausstehend. Bitte neu verbinden.")

    email = session["email"]
    password = session["password"]

    session["code"] = code
    session["mfa_provided"].set()

    # Wait for login to complete
    session["done"].wait(timeout=15)

    result = session.get("result", {})
    _login_sessions.pop(user_id, None)

    if result.get("ok"):
        return {
            "ok": True,
            "display_name": result.get("display_name", email),
            "email": email,
            "password": password,
        }
    raise Exception(result.get("error", "Login fehlgeschlagen"))


def _garmin_session_from_cookies(jwt_web: str, sso_guid: str):
    """Create a requests session using browser cookies for direct Garmin API access."""
    import requests as req
    s = req.Session()
    s.cookies.set("JWT_WEB", jwt_web, domain=".connect.garmin.com")
    s.cookies.set("GARMIN-SSO", "1", domain=".garmin.com")
    if sso_guid:
        s.cookies.set("GARMIN-SSO-CUST-GUID", sso_guid, domain=".garmin.com")
    s.headers.update({
        "NK": "NT",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
    })
    return s


def _ghd_client_from_tokens(di_token: str, di_refresh: str, di_client_id: str):
    """Create a garmin_health_data client from stored DI tokens."""
    from garmin_health_data.garmin_client.client import GarminClient
    client = GarminClient()
    client.di_token = di_token
    client.di_refresh_token = di_refresh
    client.di_client_id = di_client_id
    return client


def sync_activities_browser(user_id: int, di_token: str, di_refresh: str, days: int = 30) -> int:
    """Sync activities using DI tokens from garmin_health_data."""
    from datetime import date, timedelta
    import requests as req

    today = date.today()
    start = (today - timedelta(days=days)).isoformat()

    # Use DI Bearer token directly
    s = req.Session()
    s.headers.update({
        "Authorization": f"Bearer {di_token}",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
        "NK": "NT",
        "X-Requested-With": "XMLHttpRequest",
    })

    r = s.get("https://connect.garmin.com/activitylist-service/activities/search/activities", params={
        "startDate": start, "endDate": today.isoformat(), "start": 0, "limit": 100,
    })
    if r.status_code == 401:
        raise Exception("DI Token abgelaufen – bitte garmin_interactive_login.py erneut ausführen.")
    r.raise_for_status()
    activities = r.json() if isinstance(r.json(), list) else r.json().get("activityList", [])

    csv_file = _user_csv(user_id, "garmin_activities.csv")
    HEADERS = ["Date", "Time", "activityName", "sportType", "duration", "elapsedDuration",
               "movingDuration", "distance", "averageSpeed", "maxSpeed", "averageHR", "maxHR",
               "hrTimeInZone_1", "hrTimeInZone_2", "hrTimeInZone_3", "hrTimeInZone_4", "hrTimeInZone_5",
               "avgPower", "maxPower", "normPower", "avgCadence", "maxCadence",
               "totalAscent", "totalDescent", "steps", "avgStrideLength",
               "avgStrokes", "totalStrokes", "poolLength", "numLaps",
               "calories", "trainingEffectLabel", "activityTrainingLoad",
               "aerobicEffect", "anaerobicEffect", "vo2Max", "lactateThreshold", "activityId"]

    rows = []
    for act in activities:
        d = act.get("startTimeLocal", "")
        atype = str(act.get("activityType", {}).get("typeKey", "")).lower()
        sport = "cycling" if any(x in atype for x in ["cycl","bik","ride","virtual"]) else \
                "running" if any(x in atype for x in ["run","treadmill"]) else "other"
        rows.append([
            d[:10], d[11:], act.get("activityName","Activity"), sport,
            act.get("duration",0), act.get("elapsedDuration",0), act.get("movingDuration",0),
            act.get("distance",0), act.get("averageSpeed",0), act.get("maxSpeed",0),
            act.get("averageHR"), act.get("maxHR"),
            None, None, None, None, None,
            act.get("averagePower") or act.get("avgPower"), act.get("maxPower"),
            act.get("normPower") or act.get("normalizedPower"),
            act.get("averageBikingCadenceInRevPerMinute") or act.get("averageCadence"),
            act.get("maxCadence"), act.get("elevationGain"), act.get("elevationLoss"),
            None, None, None, None, None, None,
            act.get("calories"), None, act.get("activityTrainingLoad"),
            None, None, None, None, act.get("activityId",""),
        ])

    import csv as csv_mod
    rows.sort(key=lambda x: (x[0], x[1]), reverse=True)
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv_mod.writer(f)
        writer.writerow(HEADERS)
        writer.writerows(rows)
    return len(rows)


def sync_health_browser(user_id: int, di_token: str, di_refresh: str, days: int = 7) -> int:
    """Sync health stats using DI Bearer token."""
    import csv as csv_mod, requests as req
    from datetime import date, timedelta

    s = req.Session()
    s.headers.update({
        "Authorization": f"Bearer {di_token}",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
        "NK": "NT",
        "X-Requested-With": "XMLHttpRequest",
    })

    # Get display name first
    display_name = None
    try:
        r = s.get("https://connect.garmin.com/userprofile-service/socialProfile")
        if r.status_code == 200 and r.text.startswith("{"):
            display_name = r.json().get("displayName")
    except Exception:
        pass

    if not display_name:
        raise Exception("DI Token abgelaufen – bitte garmin_interactive_login.py erneut ausführen.")

    csv_file = _user_csv(user_id, "garmin_stats.csv")
    HEADERS = ["Date", "Weight (lbs)", "Muscle Mass (lbs)", "Body Fat %", "Water %",
               "Sleep Total (hr)", "Sleep Deep (hr)", "Sleep REM (hr)", "Sleep Score",
               "RHR", "Min HR", "Max HR", "Avg Stress", "Respiration", "SpO2",
               "VO2 Max", "Training Status", "HRV Status", "HRV Avg",
               "BP Systolic", "BP Diastolic", "Steps", "Step Goal", "Cals Total", "Cals Active", "Activities"]

    existing_rows = []
    if os.path.isfile(csv_file):
        with open(csv_file, "r", newline="", encoding="utf-8-sig") as f:
            reader = csv_mod.reader(f)
            all_data = list(reader)
            if all_data:
                existing_rows = [r for r in all_data[1:] if r]

    today = date.today()
    synced = 0
    for i in range(days):
        day_str = (today - timedelta(days=i)).isoformat()
        existing_rows = [r for r in existing_rows if r[0] != day_str]
        try:
            rhr = steps = sleep_total = sleep_score = hrv_avg = None
            r = s.get(f"https://connect.garmin.com/usersummary-service/usersummary/daily/{display_name}",
                      params={"calendarDate": day_str})
            if r.status_code == 200 and r.text.startswith("{"):
                d = r.json()
                rhr = d.get("restingHeartRate")
                steps = d.get("totalSteps")

            r = s.get(f"https://connect.garmin.com/wellness-service/wellness/dailySleepData/{display_name}",
                      params={"date": day_str})
            if r.status_code == 200 and r.text.startswith("{"):
                sl = r.json().get("dailySleepDTO", {})
                t = sl.get("sleepTimeSeconds")
                sleep_total = round(t / 3600, 2) if t else None
                sc = sl.get("sleepScores", {})
                sleep_score = sc.get("overall", {}).get("value") if sc else None

            existing_rows.append([
                day_str, None, None, None, None,
                sleep_total, None, None, sleep_score,
                rhr, None, None, None, None, None,
                None, None, None, hrv_avg,
                None, None, steps, None, None, None, ""
            ])
            synced += 1
        except Exception:
            pass

    existing_rows.sort(key=lambda x: x[0] if x else "", reverse=True)
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv_mod.writer(f)
        writer.writerow(HEADERS)
        writer.writerows(existing_rows)
    return synced


def _resume_garmin(token_dir: str):
    """Resume Garmin session from saved tokens and restore display_name."""
    import garth
    from garminconnect import Garmin

    garth.resume(token_dir)
    api = Garmin("dummy", "dummy")
    api.garth = garth.client

    # Restore display_name needed for get_user_summary
    try:
        api.display_name = (
            api.garth.profile.get("displayName")
            or api.garth.profile.get("username")
            or api.garth.profile.get("sub")
        )
    except Exception:
        pass

    return api


def sync_activities(user_id: int, days: int = 30) -> int:
    """Sync last N days of activities for a user. Returns number of activities synced."""
    token_dir = _user_token_dir(user_id)
    csv_file = _user_csv(user_id, "garmin_activities.csv")

    api = _resume_garmin(token_dir)

    start = (date.today() - timedelta(days=days)).isoformat()
    end = date.today().isoformat()
    activities = api.get_activities_by_date(start, end) or []

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

    rows = []
    for act in activities:
        start_local = act.get("startTimeLocal", "")
        avg_cadence = (
            act.get("averageBikingCadenceInRevPerMinute") or
            act.get("averageCyclingCadence") or
            act.get("averageCadence") or
            act.get("avgCadence")
        )
        norm_p = act.get("normPower") or act.get("normalizedPower")
        atype = str(act.get("activityType", {}).get("typeKey", "")).lower()
        if any(x in atype for x in ["run", "treadmill"]):
            sport = "running"
        elif any(x in atype for x in ["cycl", "bik", "ride", "virtual"]):
            sport = "cycling"
        else:
            sport = "other"

        rows.append([
            start_local[:10], start_local[11:], act.get("activityName", "Activity"), sport,
            act.get("duration", 0), act.get("elapsedDuration", 0), act.get("movingDuration", 0), act.get("distance", 0),
            act.get("averageSpeed", 0), act.get("maxSpeed", 0), act.get("averageHR"), act.get("maxHR"),
            act.get("hrTimeInZone_1"), act.get("hrTimeInZone_2"), act.get("hrTimeInZone_3"),
            act.get("hrTimeInZone_4"), act.get("hrTimeInZone_5"),
            act.get("averagePower") or act.get("avgPower"),
            act.get("maxPower"), norm_p, avg_cadence, act.get("maxCadence"),
            act.get("elevationGain"), act.get("elevationLoss"), act.get("steps"), act.get("avgStrideLength"),
            act.get("avgStrokes"), act.get("strokes"), act.get("poolLength"), act.get("numLaps"),
            act.get("calories"), act.get("trainingEffectLabel"), act.get("activityTrainingLoad"),
            act.get("aerobicTrainingEffect"), act.get("anaerobicTrainingEffect"),
            act.get("vO2MaxValue"), act.get("lactateThresholdHeartRate"), act.get("activityId"),
        ])

    from .data_manager import load_blacklist
    blacklist = load_blacklist(user_id)
    if blacklist:
        rows = [r for r in rows if (r[0], r[2]) not in blacklist]  # r[0]=date, r[2]=activityName

    rows.sort(key=lambda x: (x[0], x[1]), reverse=True)
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(HEADERS)
        writer.writerows(rows)

    return len(rows)


def sync_health(user_id: int, days: int = 7) -> int:
    """Sync last N days of health/stats data for a user. Returns number of days synced."""
    token_dir = _user_token_dir(user_id)
    csv_file = _user_csv(user_id, "garmin_stats.csv")

    api = _resume_garmin(token_dir)

    def get_safe(data, *keys):
        try:
            for k in keys:
                data = data[k]
            return data
        except Exception:
            return None

    HEADERS = [
        "Date", "Weight (lbs)", "Muscle Mass (lbs)", "Body Fat %", "Water %",
        "Sleep Total (hr)", "Sleep Deep (hr)", "Sleep REM (hr)", "Sleep Score",
        "RHR", "Min HR", "Max HR", "Avg Stress", "Respiration", "SpO2",
        "VO2 Max", "Training Status", "HRV Status", "HRV Avg",
        "BP Systolic", "BP Diastolic", "Steps", "Step Goal", "Cals Total", "Cals Active", "Activities"
    ]

    # Load existing data
    existing_dates = set()
    rows = []
    if os.path.isfile(csv_file):
        with open(csv_file, "r", newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            all_data = list(reader)
            if all_data:
                rows = [r for r in all_data[1:] if r]
                existing_dates = {r[0] for r in rows if r}

    today = date.today()
    missing = [
        (today - timedelta(days=i)).isoformat()
        for i in range(days)
        if (today - timedelta(days=i)).isoformat() not in existing_dates
    ]
    # Always refresh today AND yesterday (Garmin finalizes sleep/steps hours later)
    today_str = today.isoformat()
    yesterday_str = (today - timedelta(days=1)).isoformat()
    for refresh_str in [today_str, yesterday_str]:
        rows = [r for r in rows if r[0] != refresh_str]
        if refresh_str not in missing:
            missing.append(refresh_str)

    synced = 0
    for day_str in sorted(missing):
        try:
            rows = [r for r in rows if r[0] != day_str]

            # Basic stats
            rhr = min_hr = max_hr = stress = steps = vo2 = spo2 = resp = None
            cals_total = cals_active = cals_goal = None
            try:
                s = api.get_user_summary(day_str)
                rhr = get_safe(s, "restingHeartRate")
                min_hr = get_safe(s, "minHeartRate")
                max_hr = get_safe(s, "maxHeartRate")
                stress = get_safe(s, "averageStressLevel")
                steps = get_safe(s, "totalSteps")
                vo2 = get_safe(s, "vo2Max")
                spo2 = get_safe(s, "averageSpO2")
                resp = get_safe(s, "averageRespirationValue")
                cals_total = get_safe(s, "totalKilocalories")
                cals_active = get_safe(s, "activeKilocalories")
                cals_goal = get_safe(s, "dailyStepGoal")
            except Exception:
                pass

            # VO2 Max Fallback 1: get_max_metrics (most reliable source)
            if vo2 is None:
                try:
                    if hasattr(api, "get_max_metrics"):
                        max_metrics = api.get_max_metrics(day_str)
                        if max_metrics:
                            for metric in (max_metrics if isinstance(max_metrics, list) else [max_metrics]):
                                vo2 = (get_safe(metric, "generic", "vo2MaxPreciseValue")
                                       or get_safe(metric, "vo2MaxPreciseValue"))
                                if vo2:
                                    break
                except Exception:
                    pass

            # VO2 Max Fallback 2: training status
            if vo2 is None:
                try:
                    if hasattr(api, "get_training_status"):
                        t_status = api.get_training_status(day_str)
                        vo2 = (get_safe(t_status, "vo2MaxValue")
                               or get_safe(t_status, "mostRecentTerminatedTrainingStatus", "vo2MaxValue"))
                except Exception:
                    pass

            # Sleep
            sleep_total = sleep_deep = sleep_rem = sleep_score = None
            try:
                sl = api.get_sleep_data(day_str)
                sleep_total = get_safe(sl, "dailySleepDTO", "sleepTimeSeconds")
                sleep_deep = get_safe(sl, "dailySleepDTO", "deepSleepSeconds")
                sleep_rem = get_safe(sl, "dailySleepDTO", "remSleepSeconds")
                sleep_score = get_safe(sl, "dailySleepDTO", "sleepScores", "overall", "value")
                if sleep_total: sleep_total = round(sleep_total / 3600, 2)
                if sleep_deep: sleep_deep = round(sleep_deep / 3600, 2)
                if sleep_rem: sleep_rem = round(sleep_rem / 3600, 2)
            except Exception:
                pass

            # HRV
            hrv_status = hrv_avg = None
            try:
                h = api.get_hrv_data(day_str) if hasattr(api, "get_hrv_data") else \
                    api.connectapi(f"/hrv-service/hrv/daily/{day_str}")
                hrv_status = get_safe(h, "hrvSummary", "status")
                hrv_avg = (get_safe(h, "hrvSummary", "weeklyAverage") or
                           get_safe(h, "hrvSummary", "lastNightAvg") or
                           get_safe(h, "lastNightAvg"))
            except Exception:
                pass

            rows.append([
                day_str, None, None, None, None,
                sleep_total, sleep_deep, sleep_rem, sleep_score,
                rhr, min_hr, max_hr, stress, resp, spo2,
                vo2, None, hrv_status, hrv_avg,
                None, None, steps, cals_goal, cals_total, cals_active, ""
            ])
            synced += 1
        except Exception:
            pass

    rows.sort(key=lambda x: x[0] if x else "", reverse=True)
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(HEADERS)
        writer.writerows(rows)

    return synced
