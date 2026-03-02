"""
CSV read/write operations – single source of truth for file access.
"""
import os
import io
import pandas as pd
from datetime import datetime, date
from dotenv import load_dotenv

load_dotenv()

_SAVE_PATH = os.getenv("SAVE_PATH", os.path.expanduser("~/Documents/AI_Fitness-main"))

# Legacy single-user paths (für Streamlit Kompatibilität)
FILE_STATS = os.path.join(_SAVE_PATH, "garmin_stats.csv")
FILE_ACT = os.path.join(_SAVE_PATH, "garmin_activities.csv")
FILE_CHECKIN = os.path.join(_SAVE_PATH, "daily_checkin.csv")


def _user_files(user_id: int | None) -> tuple[str, str, str]:
    """Return (stats_path, act_path, checkin_path) for a given user."""
    if user_id is None:
        return FILE_STATS, FILE_ACT, FILE_CHECKIN
    base = os.path.join(_SAVE_PATH, "users", str(user_id))
    os.makedirs(base, exist_ok=True)
    return (
        os.path.join(base, "garmin_stats.csv"),
        os.path.join(base, "garmin_activities.csv"),
        os.path.join(base, "daily_checkin.csv"),
    )

# Column aliases: Garmin exports can be English or German
_ACT_COL_MAP = {
    "Training Load": "activityTrainingLoad",
    "Norm. Power": "normPower",
    "Avg HR": "averageHR",
    "Distance": "distance",
    "Avg Cadence": "avgCadence",
    "Activity Name": "activityName",
}
_STATS_COL_MAP = {
    "Sleep Score": "Sleep Score",
    "Resting HR": "RHR",
    "HRV": "HRV Avg",
}


def _read_csv_safe(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        df = pd.read_csv(path, on_bad_lines="warn")
        df.rename(columns=_ACT_COL_MAP, inplace=True)
        df.rename(columns=_STATS_COL_MAP, inplace=True)
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            df.dropna(subset=["Date"], inplace=True)
            df.sort_values("Date", inplace=True)
        return df
    except Exception:
        return pd.DataFrame()


def load_stats(user_id: int | None = None) -> pd.DataFrame:
    path, _, _ = _user_files(user_id)
    return _read_csv_safe(path)


def load_activities(user_id: int | None = None) -> pd.DataFrame:
    _, path, _ = _user_files(user_id)
    return _read_csv_safe(path)


def load_checkins(user_id: int | None = None) -> pd.DataFrame:
    _, _, path = _user_files(user_id)
    df = _read_csv_safe(path)
    for col in ["Schlaf", "Stress", "Energie", "Load_Gestern",
                "Muskeln", "Ernahrung", "Mental", "Gesundheit", "RPE", "Feel"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def get_checkin_today(user_id: int | None = None) -> dict | None:
    df = load_checkins(user_id)
    if df.empty or "Date" not in df.columns:
        return None
    today = pd.Timestamp.now().normalize()
    row = df[df["Date"].dt.normalize() == today]
    if row.empty:
        return None
    r = row.iloc[-1]
    return {
        "date": str(r["Date"].date()),
        "schlaf": float(r.get("Schlaf", 0) or 0),
        "stress": float(r.get("Stress", 0) or 0),
        "energie": float(r.get("Energie", 0) or 0),
        "load_gestern": float(r.get("Load_Gestern", 0) or 0),
        "muskeln": float(r.get("Muskeln", 0) or 0),
        "ernahrung": float(r.get("Ernahrung", 0) or 0),
        "mental": float(r.get("Mental", 0) or 0),
        "gesundheit": float(r.get("Gesundheit", 0) or 0),
        "rpe": float(r.get("RPE", 0) or 0) if "RPE" in r.index else None,
        "feel": float(r.get("Feel", 0) or 0) if "Feel" in r.index else None,
    }


def save_checkin(data: dict, user_id: int | None = None) -> None:
    """Write or update a check-in row in the CSV."""
    _, _, checkin_path = _user_files(user_id)
    df = load_checkins(user_id)
    today_str = data["date"]

    new_row = {
        "Date": today_str,
        "Schlaf": data.get("schlaf"),
        "Stress": data.get("stress"),
        "Energie": data.get("energie"),
        "Load_Gestern": data.get("load_gestern"),
        "Muskeln": data.get("muskeln"),
        "Ernahrung": data.get("ernahrung"),
        "Mental": data.get("mental"),
        "Gesundheit": data.get("gesundheit"),
    }

    if not df.empty and "Date" in df.columns:
        df["_date_str"] = df["Date"].dt.strftime("%Y-%m-%d")
        df = df[df["_date_str"] != today_str].drop(columns=["_date_str"])

    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_csv(checkin_path, index=False)


def save_matrix(date_str: str, rpe: float, feel: float, user_id: int | None = None) -> None:
    """Update RPE and Feel for a given date in the check-in CSV."""
    _, _, checkin_path = _user_files(user_id)
    df = load_checkins(user_id)

    if df.empty or "Date" not in df.columns:
        df = pd.DataFrame([{"Date": date_str, "RPE": rpe, "Feel": feel}])
        df.to_csv(checkin_path, index=False)
        return

    df["_date_str"] = df["Date"].dt.strftime("%Y-%m-%d")
    mask = df["_date_str"] == date_str

    if mask.any():
        df.loc[mask, "RPE"] = rpe
        df.loc[mask, "Feel"] = feel
    else:
        new_row = {"Date": date_str, "RPE": rpe, "Feel": feel}
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

    df.drop(columns=["_date_str"], inplace=True)
    df.to_csv(checkin_path, index=False)


def delete_activity(date_str: str, name: str, user_id: int | None = None) -> bool:
    """Remove a single activity row from garmin_activities.csv. Returns True if found."""
    _, act_path, _ = _user_files(user_id)
    df = load_activities(user_id)
    if df.empty:
        return False
    mask = (df["Date"].dt.strftime("%Y-%m-%d") == date_str) & (df["activityName"] == name)
    if not mask.any():
        return False
    df = df[~mask]
    df.to_csv(act_path, index=False)
    return True


def merge_upload(file_bytes: bytes, target: str, user_id: int | None = None) -> int:
    """
    Merge uploaded CSV bytes into the target file.
    Returns number of new rows added.
    """
    try:
        new_df = pd.read_csv(io.BytesIO(file_bytes), on_bad_lines="warn")
    except Exception as e:
        raise ValueError(f"Cannot parse uploaded CSV: {e}")

    stats_path, act_path, _ = _user_files(user_id)
    path = stats_path if target == "stats" else act_path
    existing = _read_csv_safe(path)

    if existing.empty:
        merged = new_df
    else:
        merged = pd.concat([existing, new_df], ignore_index=True)
        if "Date" in merged.columns:
            merged["Date"] = pd.to_datetime(merged["Date"], errors="coerce")
            merged.drop_duplicates(subset=["Date"], keep="last", inplace=True)
            merged.sort_values("Date", inplace=True)

    before = len(existing)
    merged.to_csv(path, index=False)
    return len(merged) - before
