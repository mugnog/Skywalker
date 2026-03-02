"""
Pure calculation functions – no I/O, no frameworks.
Extracted from skywalker_dashboard.py.
"""
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

BASE_FTP = 230
TARGET_FTP = 250
FTP_WINDOW_DAYS = 90
CTL_SPAN = 42
ATL_SPAN = 7


def compute_ftp(df_act: pd.DataFrame) -> float:
    """Return FTP – manual override from FTP_OVERRIDE env var takes priority."""
    override = os.getenv("FTP_OVERRIDE")
    if override:
        try:
            return float(override)
        except ValueError:
            pass
    if df_act.empty or "normPower" not in df_act.columns:
        return BASE_FTP
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=FTP_WINDOW_DAYS)
    recent = df_act[df_act["Date"] >= cutoff]
    max_np = pd.to_numeric(recent["normPower"], errors="coerce").max()
    if pd.isna(max_np) or max_np == 0:
        return BASE_FTP
    return round(max_np * 0.95)


def _daily_tss(df_act: pd.DataFrame, days: int) -> pd.DataFrame:
    """Build a continuous daily TSS series with 0 for missing days."""
    end = pd.Timestamp.now().normalize()
    start = end - pd.Timedelta(days=days)
    date_range = pd.date_range(start, end, freq="D")

    df = df_act.copy()
    df["Date"] = pd.to_datetime(df["Date"]).dt.normalize()
    daily = (
        df.groupby("Date")["activityTrainingLoad"]
        .sum()
        .reindex(date_range, fill_value=0)
        .reset_index()
    )
    daily.columns = ["Date", "TSS"]
    return daily


def compute_ctl_atl_tsb(df_act: pd.DataFrame, days: int = 90) -> pd.DataFrame:
    """Return DataFrame with Date, CTL, ATL, TSB columns."""
    daily = _daily_tss(df_act, days)
    daily["CTL"] = daily["TSS"].ewm(span=CTL_SPAN, adjust=False).mean()
    daily["ATL"] = daily["TSS"].ewm(span=ATL_SPAN, adjust=False).mean()
    daily["TSB"] = daily["CTL"] - daily["ATL"]
    return daily


def compute_weekly_load(df_act: pd.DataFrame) -> float:
    """Sum of TSS from last 7 days."""
    if df_act.empty or "activityTrainingLoad" not in df_act.columns:
        return 0.0
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=7)
    recent = df_act[df_act["Date"] >= cutoff]
    return float(pd.to_numeric(recent["activityTrainingLoad"], errors="coerce").sum())


def compute_hrv_status(df_stats: pd.DataFrame) -> dict:
    """HRV readiness: compare latest reading to 7-day baseline."""
    if df_stats.empty or "HRV Avg" not in df_stats.columns:
        return {"status": "unknown", "color": "#888888", "current": 0.0, "baseline": 0.0}

    sorted_df = df_stats.sort_values("Date", ascending=False)
    hrv_series = pd.to_numeric(sorted_df["HRV Avg"], errors="coerce")
    latest = hrv_series.iloc[0]
    baseline = hrv_series.head(7).mean()

    if pd.isna(latest) or pd.isna(baseline) or baseline == 0:
        return {"status": "unknown", "color": "#888888", "current": 0.0, "baseline": 0.0}

    ratio = latest / baseline
    if ratio >= 0.95:
        status, color = "green", "#00C853"
    elif ratio >= 0.85:
        status, color = "yellow", "#FFD600"
    else:
        status, color = "red", "#FF1744"

    return {
        "status": status,
        "color": color,
        "current": round(float(latest), 1),
        "baseline": round(float(baseline), 1),
        "ratio": round(float(ratio), 3),
    }


def compute_combined_status(
    hrv_status: dict,
    tsb: float,
    checkin: dict | None,
) -> dict:
    """
    Kombinierter Readiness-Status aus HRV + TSB + Check-in.
    Gibt label, color, score (0-10) und Erklärung zurück.
    """
    scores = []

    # HRV: green=10, yellow=6, red=2, unknown=5
    hrv_score = {"green": 10, "yellow": 6, "red": 2, "unknown": 5}.get(hrv_status.get("status", "unknown"), 5)
    scores.append(("HRV", hrv_score))

    # TSB: >10=10, 0-10=8, -10-0=5, <-10=2
    if tsb > 10:
        tsb_score = 10
    elif tsb >= 0:
        tsb_score = 8
    elif tsb >= -10:
        tsb_score = 5
    else:
        tsb_score = 2
    scores.append(("TSB", tsb_score))

    # Check-in (falls vorhanden)
    if checkin:
        checkin_score, _ = compute_readiness(checkin)
        scores.append(("Check-in", checkin_score))

    total = sum(s for _, s in scores) / len(scores)

    if total >= 8.5:
        label, color = "RACE READY 🔥", "#00C853"
    elif total >= 7:
        label, color = "BEREIT 💪", "#00C853"
    elif total >= 5.5:
        label, color = "MODERAT 🟡", "#FFD600"
    elif total >= 4:
        label, color = "MÜDE 😴", "#FF6D00"
    else:
        label, color = "ERHOLEN 🛋️", "#FF1744"

    components = {name: round(s, 1) for name, s in scores}

    return {
        "label": label,
        "color": color,
        "score": round(total, 1),
        "components": components,
    }


def compute_readiness(checkin_row: dict) -> tuple[float, str]:
    """
    Average 8 check-in metrics into a single readiness score.
    Returns (score 0-10, label string).
    """
    stress_inv = 11 - checkin_row.get("stress", 5)
    load_inv = 11 - checkin_row.get("load_gestern", 5)

    values = [
        checkin_row.get("schlaf", 5),
        stress_inv,
        checkin_row.get("energie", 5),
        load_inv,
        checkin_row.get("muskeln", 5),
        checkin_row.get("ernahrung", 5),
        checkin_row.get("mental", 5),
        checkin_row.get("gesundheit", 5),
    ]
    score = round(sum(values) / len(values), 1)

    if score >= 9:
        label = "RACE READY 🔥"
    elif score >= 8:
        label = "SOLID 💪"
    elif score >= 6:
        label = "TIRED 😴"
    else:
        label = "REST DAY 🛋️"

    return score, label


def compute_training_distribution(df_act: pd.DataFrame, ftp: float) -> dict:
    """
    Categorize activities into Zone 2 / Sweet Spot / High Intensity based on NP vs FTP.
    Returns percentage dict.
    """
    if df_act.empty or "normPower" not in df_act.columns or ftp == 0:
        return {"Zone2": 0, "SweetSpot": 0, "HighIntensity": 0}

    df = df_act.copy()
    df["IF"] = pd.to_numeric(df["normPower"], errors="coerce") / ftp

    total = len(df.dropna(subset=["IF"]))
    if total == 0:
        return {"Zone2": 0, "SweetSpot": 0, "HighIntensity": 0}

    zone2 = (df["IF"] < 0.84).sum()
    sweet = ((df["IF"] >= 0.84) & (df["IF"] < 1.05)).sum()
    high = (df["IF"] >= 1.05).sum()

    return {
        "Zone2": round(zone2 / total * 100),
        "SweetSpot": round(sweet / total * 100),
        "HighIntensity": round(high / total * 100),
    }
