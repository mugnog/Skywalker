import garth
from garminconnect import Garmin
import json
import os
from dotenv import load_dotenv

load_dotenv()
TOKEN_DIR = ".garth"

def main():
    try:
        garth.resume(TOKEN_DIR)
        api = Garmin("dummy", "dummy")
        api.garth = garth.client
        
        print("Suche letzte Aktivität...")
        activities = api.get_activities(0, 1) # Nur die allerletzte
        
        if activities:
            act = activities[0]
            print(f"Aktivität gefunden: {act.get('activityName')}")
            print("-" * 30)
            
            # Suche nach allen Keys, die mit Cadence oder Power zu tun haben
            interesting_keys = [k for k in act.keys() if "cadence" in k.lower() or "power" in k.lower() or "speed" in k.lower()]
            
            for k in interesting_keys:
                print(f"{k}: {act.get(k)}")
            
            # Speichere die ganze Datei als JSON zum Nachschauen
            with open("debug_activity.json", "w") as f:
                json.dump(act, f, indent=2)
            print("-" * 30)
            print("Alle interessanten Werte wurden oben ausgegeben.")
            print("Zusätzlich wurde 'debug_activity.json' erstellt.")
            
    except Exception as e:
        print(f"Fehler: {e}")

if __name__ == "__main__":
    main()