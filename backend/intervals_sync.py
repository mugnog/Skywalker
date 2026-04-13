"""
intervals.icu API integration – fetch planned workouts and activities.
"""
import os
import requests
from datetime import date, timedelta

INTERVALS_BASE = "https://intervals.icu/api/v1"


def _auth(api_key: str):
    return ("API_KEY", api_key)


def get_planned_workouts(athlete_id: str, api_key: str, days: int = 7) -> list:
    """Fetch planned workouts for the next N days."""
    today = date.today()
    end = today + timedelta(days=days)
    url = f"{INTERVALS_BASE}/athlete/{athlete_id}/events"
    params = {
        "oldest": today.isoformat(),
        "newest": end.isoformat(),
    }
    resp = requests.get(url, auth=_auth(api_key), params=params, timeout=10)
    resp.raise_for_status()
    events = resp.json()

    workouts = []
    for e in events:
        if e.get("category") not in ("WORKOUT", "NOTE"):
            continue
        workouts.append({
            "date": e.get("start_date_local", "")[:10],
            "name": e.get("name", ""),
            "description": e.get("description", "") or "",
            "load": e.get("load"),
            "duration_mins": round(e.get("moving_time", 0) / 60) if e.get("moving_time") else None,
            "sport": e.get("type", ""),
        })
    return workouts


def get_weekly_plan_text(athlete_id: str, api_key: str) -> str:
    """Return a plain-text summary of the next 7 days for the coach prompt."""
    try:
        workouts = get_planned_workouts(athlete_id, api_key, days=7)
        if not workouts:
            return "Kein intervals.icu Wochenplan gefunden."
        lines = ["intervals.icu Wochenplan (nächste 7 Tage):"]
        for w in workouts:
            dur = f" ({w['duration_mins']} min)" if w['duration_mins'] else ""
            desc = f" – {w['description'][:80]}" if w['description'] else ""
            lines.append(f"  {w['date']} [{w['sport']}] {w['name']}{dur}{desc}")
        return "\n".join(lines)
    except Exception as e:
        return f"intervals.icu nicht erreichbar: {e}"
