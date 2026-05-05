"""
Garmin Login – nur MFA Code eingeben, Rest automatisch.
Ausführen: python3 garmin_interactive_login.py
"""
import warnings
warnings.filterwarnings("ignore")
import requests, json, os, sys

BACKEND_URL = "https://mugnog.fly.dev"
SKY_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwiZW1haWwiOiJ1bG1lcm90dG9zMzMzQGdtYWlsLmNvbSIsImV4cCI6MTc3ODU5ODIxMH0.OpTRpRunznNBPGqJ8z6ODRJWlYIt7RSEr5i39I4AWLw"

def mfa_prompt():
    print("\n📧 Code per Email erhalten?")
    return input("Code eingeben: ").strip()

print("Garmin Login startet (30-45 Sekunden)...\n")

sky_token = SKY_TOKEN

# Garmin Login
from garmin_health_data.garmin_client.client import GarminClient
client = GarminClient()
try:
    client.login("ulmerottos333@gmail.com", "Tdfosclar396", prompt_mfa=mfa_prompt)
except Exception as e:
    print(f"❌ Fehler: {e}"); sys.exit(1)

di_token     = getattr(client, "di_token", None)
di_refresh   = getattr(client, "di_refresh_token", None)
di_client_id = getattr(client, "di_client_id", None)

if not di_token:
    print("❌ Keine Tokens – Login fehlgeschlagen."); sys.exit(1)

print("✓ Login erfolgreich!")

# Ins Backend hochladen
r = requests.post(f"{BACKEND_URL}/api/auth/garmin-di-tokens",
    headers={"Authorization": f"Bearer {sky_token}"},
    json={"di_token": di_token, "di_refresh_token": di_refresh, "di_client_id": di_client_id})

if r.status_code == 200:
    print("✓ Fertig! Garmin Sync funktioniert jetzt.")
else:
    print(f"❌ Upload fehlgeschlagen: {r.text}")
    with open("/tmp/garmin_tokens.json", "w") as f:
        json.dump({"di_token": di_token, "di_refresh_token": di_refresh, "di_client_id": di_client_id}, f)
    print("  Tokens lokal gespeichert: /tmp/garmin_tokens.json")
