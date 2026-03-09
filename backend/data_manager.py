"""
CSV read/write operations – single source of truth for file access.
"""
import os
import io
import json
import pandas as pd
from datetime import datetime, date
from dotenv import load_dotenv

load_dotenv()

_SAVE_PATH = os.getenv("SAVE_PATH", os.path.expanduser("~/Documents/AI_Fitness-main"))

# Legacy single-user paths (für Streamlit Kompatibilität)
FILE_STATS = os.path.join(_SAVE_PATH, "garmin_stats.csv")
FILE_ACT = os.path.join(_SAVE_PATH, "garmin_activities.csv")
FILE_CHECKIN = os.path.join(_SAVE_PATH, "daily_checkin.csv")


def _blacklist_path(user_id: int | None) -> str:
    if user_id is None:
        return os.path.join(_SAVE_PATH, "deleted_activities.json")
    base = os.path.join(_SAVE_PATH, "users", str(user_id))
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "deleted_activities.json")


def load_blacklist(user_id: int | None = None) -> set[tuple[str, str]]:
    """Returns a set of (date_str, name) tuples for deleted activities."""
    path = _blacklist_path(user_id)
    if not os.path.exists(path):
        return set()
    try:
        with open(path) as f:
            data = json.load(f)
        return {(e["date"], e["name"]) for e in data}
    except Exception:
        return set()


def _add_to_blacklist(date_str: str, name: str, user_id: int | None) -> None:
    path = _blacklist_path(user_id)
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception:
        data = []
    if not any(e["date"] == date_str and e["name"] == name for e in data):
        data.append({"date": date_str, "name": name})
    with open(path, "w") as f:
        json.dump(data, f)


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
    df = _read_csv_safe(path)
    if df.empty or "Date" not in df.columns or "activityName" not in df.columns:
        return df
    blacklist = load_blacklist(user_id)
    if blacklist:
        mask = df.apply(
            lambda r: (r["Date"].strftime("%Y-%m-%d"), r["activityName"]) in blacklist, axis=1
        )
        df = df[~mask]
    return df


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

    def _f(key, default=5.0):
        v = r.get(key, default)
        return float(default if pd.isna(v) else v)

    return {
        "date": str(r["Date"].date()),
        "schlaf":       _f("Schlaf"),
        "stress":       _f("Stress"),
        "energie":      _f("Energie"),
        "load_gestern": _f("Load_Gestern"),
        "muskeln":      _f("Muskeln"),
        "ernahrung":    _f("Ernahrung"),
        "mental":       _f("Mental"),
        "gesundheit":   _f("Gesundheit"),
        "rpe":   _f("RPE")  if "RPE"  in r.index and not pd.isna(r.get("RPE"))  else None,
        "feel":  _f("Feel") if "Feel" in r.index and not pd.isna(r.get("Feel")) else None,
    }


def get_checkin_recent(user_id: int | None = None, max_days: int = 2) -> dict | None:
    """Return the most recent check-in within the last max_days days (for coach context)."""
    df = load_checkins(user_id)
    if df.empty or "Date" not in df.columns:
        return None
    cutoff = pd.Timestamp.now().normalize() - pd.Timedelta(days=max_days)
    recent = df[df["Date"].dt.normalize() >= cutoff].sort_values("Date", ascending=False)
    if recent.empty:
        return None
    r = recent.iloc[0]

    def _f(key, default=5.0):
        v = r.get(key, default)
        return float(default if pd.isna(v) else v)

    return {
        "date": str(r["Date"].date()),
        "schlaf":    _f("Schlaf"),
        "energie":   _f("Energie"),
        "muskeln":   _f("Muskeln"),
        "ernahrung": _f("Ernahrung"),
        "mental":    _f("Mental"),
        "gesundheit": _f("Gesundheit"),
        "rpe":  _f("RPE")  if "RPE"  in r.index and not pd.isna(r.get("RPE"))  else None,
        "feel": _f("Feel") if "Feel" in r.index and not pd.isna(r.get("Feel")) else None,
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
    """Remove a single activity row and blacklist it so Garmin sync won't restore it."""
    _, act_path, _ = _user_files(user_id)
    df = _read_csv_safe(act_path)  # raw read without blacklist filter
    if df.empty:
        _add_to_blacklist(date_str, name, user_id)
        return True
    mask = (df["Date"].dt.strftime("%Y-%m-%d") == date_str) & (df["activityName"] == name)
    df = df[~mask]
    df.to_csv(act_path, index=False)
    _add_to_blacklist(date_str, name, user_id)
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
