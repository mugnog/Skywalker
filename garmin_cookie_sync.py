"""
Garmin Cookie Sync – umgeht den blockierten SSO-Endpoint.
Nutzt Browser-Cookies um direkt mit der Garmin Connect API zu sprechen.
"""
import requests
import json
import csv
import sys
from datetime import date, timedelta

# ── Konfiguration ─────────────────────────────────────────────────────────────
JWT_WEB = input("JWT_WEB Cookie: ").strip()
SSO_GUID = input("GARMIN-SSO-CUST-GUID Cookie: ").strip()
BACKEND_URL = "https://mugnog.fly.dev"
JWT_SKYWALKER = input("Skywalker JWT Token (aus App → F12 → localStorage → 'token'): ").strip()

# ── Session aufbauen ──────────────────────────────────────────────────────────
s = requests.Session()
s.cookies.set("JWT_WEB", JWT_WEB, domain=".garmin.com")
s.cookies.set("GARMIN-SSO", "1", domain=".garmin.com")
s.cookies.set("GARMIN-SSO-CUST-GUID", SSO_GUID, domain=".garmin.com")
s.headers.update({
    "NK": "NT",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
    "X-Requested-With": "XMLHttpRequest",
})

BASE = "https://connect.garmin.com"

def get(path, params=None):
    r = s.get(f"{BASE}{path}", params=params)
    print(f"  {r.status_code} {path}")
    r.raise_for_status()
    return r.json()

# ── Profil holen ──────────────────────────────────────────────────────────────
print("\n1. Profil laden...")
try:
    profile = get("/modern/currentuser-service/user/info")
    display_name = profile.get("displayName") or profile.get("userName", "")
    print(f"   Eingeloggt als: {display_name}")
except Exception as e:
    print(f"   Fehler: {e}")
    print("   Versuche alternativen Endpoint...")
    try:
        profile = get("/userprofile-service/socialProfile")
        display_name = profile.get("displayName", "")
        print(f"   Eingeloggt als: {display_name}")
    except Exception as e2:
        print(f"   Auch fehlgeschlagen: {e2}")
        sys.exit(1)

# ── Aktivitäten holen ─────────────────────────────────────────────────────────
print("\n2. Aktivitäten laden (letzte 30 Tage)...")
today = date.today()
start = (today - timedelta(days=30)).isoformat()
activities = []
try:
    data = get("/activitylist-service/activities/search/activities", {
        "startDate": start,
        "endDate": today.isoformat(),
        "start": 0,
        "limit": 50,
    })
    activities = data if isinstance(data, list) else data.get("activityList", [])
    print(f"   {len(activities)} Aktivitäten gefunden")
except Exception as e:
    print(f"   Fehler: {e}")

# CSV speichern
if activities:
    rows = []
    for act in activities:
        atype = str(act.get("activityType", {}).get("typeKey", "")).lower()
        sport = "cycling" if any(x in atype for x in ["cycl","bik","ride","virtual"]) else \
                "running" if any(x in atype for x in ["run","treadmill"]) else "other"
        d = act.get("startTimeLocal","")
        distance = act.get("distance", 0) or 0
        rows.append({
            "Date": d[:10], "Time": d[11:], 
            "activityName": act.get("activityName","Activity"),
            "sportType": sport,
            "duration": act.get("duration",0),
            "distance": round(distance, 2),
            "averageHR": act.get("averageHR"),
            "maxHR": act.get("maxHR"),
            "avgPower": act.get("averagePower") or act.get("avgPower"),
            "maxPower": act.get("maxPower"),
            "normPower": act.get("normPower") or act.get("normalizedPower"),
            "avgCadence": act.get("averageBikingCadenceInRevPerMinute") or act.get("averageCadence"),
            "totalAscent": act.get("elevationGain"),
            "calories": act.get("calories"),
            "activityTrainingLoad": act.get("activityTrainingLoad"),
            "activityId": act.get("activityId",""),
        })
    
    with open("/tmp/garmin_activities.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader(); w.writerows(rows)
    print(f"   Gespeichert in /tmp/garmin_activities.csv")

    # Upload
    print("\n3. Upload zu Skywalker Backend...")
    try:
        with open("/tmp/garmin_activities.csv", "rb") as f:
            r = requests.post(
                f"{BACKEND_URL}/api/upload/activities",
                headers={"Authorization": f"Bearer {JWT_SKYWALKER}"},
                files={"file": ("garmin_activities.csv", f, "text/csv")},
            )
        print(f"   Upload: {r.status_code} – {r.text}")
    except Exception as e:
        print(f"   Upload-Fehler: {e}")

print("\nFertig!")
