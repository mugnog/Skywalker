import os
from pathlib import Path

def setup():
    print("--- Skywalker AI: Initial Setup ---")
    
    # 1. API Keys abfragen
    gemini_key = input("Gib deinen Google Gemini API Key ein: ").strip()
    garmin_user = input("Gib deine Garmin Connect Email ein: ").strip()
    garmin_pass = input("Gib dein Garmin Passwort ein (wird lokal gespeichert): ").strip()
    
    # 2. Pfade definieren
    base_path = Path.cwd()
    data_path = base_path / "data"
    data_path.mkdir(exist_ok=True)

    # 3. .env Datei schreiben
    env_content = f"""# Skywalker AI Configuration
GEMINI_API_KEY={gemini_key}
GARMIN_EMAIL={garmin_user}
GARMIN_PASSWORD={garmin_pass}
SAVE_PATH={data_path}
"""
    
    with open(".env", "w") as f:
        f.write(env_content)
    
    print(f"\n✅ .env Datei wurde erstellt!")
    print(f"✅ Ordner für Trainingsdaten erstellt: {data_path}")
    
    # 4. Garmin Login testen & Token generieren
    print("\nVersuche Garmin-Login für Token-Generierung...")
    try:
        import garth
        garth.login(garmin_user, garmin_pass)
        garth.save(".garth")
        print("✅ Garmin-Login erfolgreich! .garth Ordner wurde erstellt.")
    except Exception as e:
        print(f"❌ Garmin-Login fehlgeschlagen: {e}")
        print("Hinweis: Du kannst das später mit 'python garmin_login.py' wiederholen.")

if __name__ == "__main__":
    setup()