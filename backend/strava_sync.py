"""
Strava OAuth and activity sync integration.
"""
import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

STRAVA_CLIENT_ID = os.getenv("STRAVA_CLIENT_ID", "")
STRAVA_CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET", "")
STRAVA_WEBHOOK_VERIFY_TOKEN = os.getenv("STRAVA_WEBHOOK_VERIFY_TOKEN", "skywalker_strava_2026")
STRAVA_REDIRECT_URI = os.getenv("STRAVA_REDIRECT_URI", "https://mugnog.fly.dev/api/strava/callback")
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://skywalker-app.fly.dev")

_CYCLING_TYPES = {"ride", "virtualride", "ebikeride", "mountainbikeride", "gravelride", "handcycle"}


def get_auth_url(state: str) -> str:
    params = (
        f"client_id={STRAVA_CLIENT_ID}"
        f"&redirect_uri={STRAVA_REDIRECT_URI}"
        f"&response_type=code"
        f"&approval_prompt=auto"
        f"&scope=read,activity:read_all"
        f"&state={state}"
    )
    return f"https://www.strava.com/oauth/authorize?{params}"


def exchange_code(code: str) -> dict:
    resp = requests.post("https://www.strava.com/oauth/token", data={
        "client_id": STRAVA_CLIENT_ID,
        "client_secret": STRAVA_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()


def refresh_access_token(refresh_tok: str) -> dict:
    resp = requests.post("https://www.strava.com/oauth/token", data={
        "client_id": STRAVA_CLIENT_ID,
        "client_secret": STRAVA_CLIENT_SECRET,
        "refresh_token": refresh_tok,
        "grant_type": "refresh_token",
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_valid_token(user, db) -> str:
    """Return valid access token, refreshing if expired. Saves updated tokens to DB."""
    if not user.strava_access_token:
        raise ValueError("User has no Strava token")
    now = int(time.time())
    if user.strava_expires_at and user.strava_expires_at > now + 60:
        return user.strava_access_token
    data = refresh_access_token(user.strava_refresh_token)
    user.strava_access_token = data["access_token"]
    user.strava_refresh_token = data["refresh_token"]
    user.strava_expires_at = data["expires_at"]
    db.commit()
    return user.strava_access_token


def fetch_activity(access_token: str, activity_id: int) -> dict:
    resp = requests.get(
        f"https://www.strava.com/api/v3/activities/{activity_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_activities(access_token: str, after_ts: int = None, per_page: int = 50) -> list:
    params = {"per_page": per_page}
    if after_ts:
        params["after"] = after_ts
    resp = requests.get(
        "https://www.strava.com/api/v3/athlete/activities",
        headers={"Authorization": f"Bearer {access_token}"},
        params=params,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def activity_to_row(act: dict, ftp: float = 230) -> dict | None:
    """Convert Strava activity to our CSV row format. Returns None for non-cycling."""
    sport = act.get("sport_type", act.get("type", "")).replace("_", "").lower()
    if sport not in _CYCLING_TYPES:
        return None

    start = act.get("start_date_local", act.get("start_date", ""))[:10]
    moving_time = act.get("moving_time", 0)

    # Power – prefer weighted (normalized) over average
    avg_watts = act.get("average_watts")
    np_watts = act.get("weighted_average_watts") or avg_watts

    # TSS = (t * NP * IF) / (FTP * 3600) * 100
    tss = None
    if np_watts and ftp and ftp > 0 and moving_time > 0:
        intensity_factor = np_watts / ftp
        tss = round((moving_time * np_watts * intensity_factor) / (ftp * 3600) * 100, 1)

    return {
        "Date":                 start,
        "activityName":         act.get("name", "Strava Ride"),
        "sportType":            "cycling",
        "duration":             moving_time,
        "distance":             round((act.get("distance") or 0) / 1000, 2),  # m → km
        "averageHR":            act.get("average_heartrate"),
        "maxHR":                act.get("max_heartrate"),
        "normPower":            np_watts,
        "avgPower":             avg_watts,
        "maxPower":             act.get("max_watts"),
        "avgCadence":           act.get("average_cadence"),
        "totalAscent":          act.get("total_elevation_gain"),
        "calories":             act.get("calories"),
        "activityTrainingLoad": tss,
        "activityId":           str(act.get("id", "")),
    }


def save_activity_to_csv(row: dict, user_id: int) -> bool:
    """Append or update one activity row in the user's garmin_activities.csv."""
    import pandas as pd
    from .data_manager import _user_files, _read_csv_safe

    _, act_path, _ = _user_files(user_id)
    df = _read_csv_safe(act_path)

    # Deduplicate by activityId if column exists
    if not df.empty and "activityId" in df.columns:
        df = df[df["activityId"].astype(str) != str(row.get("activityId", ""))]

    new_df = pd.DataFrame([row])
    merged = pd.concat([df, new_df], ignore_index=True)
    if "Date" in merged.columns:
        merged["Date"] = pd.to_datetime(merged["Date"], errors="coerce")
        merged.sort_values("Date", inplace=True)
    merged.to_csv(act_path, index=False)
    return True


def register_webhook() -> dict:
    """Register Strava webhook subscription (run once after deploy)."""
    resp = requests.post(
        "https://www.strava.com/api/v3/push_subscriptions",
        data={
            "client_id": STRAVA_CLIENT_ID,
            "client_secret": STRAVA_CLIENT_SECRET,
            "callback_url": f"https://mugnog.fly.dev/api/webhook/strava",
            "verify_token": STRAVA_WEBHOOK_VERIFY_TOKEN,
        },
        timeout=15,
    )
    return resp.json()


def get_webhook_subscription() -> dict | None:
    """Check if webhook subscription exists."""
    resp = requests.get(
        "https://www.strava.com/api/v3/push_subscriptions",
        params={"client_id": STRAVA_CLIENT_ID, "client_secret": STRAVA_CLIENT_SECRET},
        timeout=15,
    )
    data = resp.json()
    return data[0] if data else None
