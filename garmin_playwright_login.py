"""
Garmin Playwright Login – öffnet echten Browser für manuellen Login.
Du loggst dich selbst ein (CAPTCHA, MFA etc.), danach werden die Tokens
automatisch extrahiert und ins Backend hochgeladen.

Ausführen: python3 garmin_playwright_login.py
"""
import json
import time
import requests
import os
from playwright.sync_api import sync_playwright

BACKEND_URL = "https://mugnog.fly.dev"


def get_skywalker_token():
    email = input("Skywalker Email: ").strip()
    password = input("Skywalker Passwort: ").strip()
    r = requests.post(f"{BACKEND_URL}/api/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def extract_oauth_tokens(page, context):
    """Versucht OAuth-Tokens aus dem Browser zu extrahieren."""
    # Warte auf erfolgreichen Login (connect.garmin.com geladen)
    page.wait_for_url("**/modern/**", timeout=120000)
    print("✓ Login erkannt! Extrahiere Tokens...")

    # Cookies auslesen
    cookies = context.cookies()
    cookie_dict = {c["name"]: c["value"] for c in cookies}

    jwt_web = cookie_dict.get("JWT_WEB", "")
    sso_guid = cookie_dict.get("GARMIN-SSO-CUST-GUID", "")

    if not jwt_web:
        print("⚠ JWT_WEB Cookie nicht gefunden – versuche alternativen Weg...")
        return None, None

    print(f"✓ JWT_WEB gefunden ({len(jwt_web)} Zeichen)")
    return jwt_web, sso_guid


def test_garmin_api(jwt_web, sso_guid):
    """Testet ob die Cookies für direkte API-Calls funktionieren."""
    s = requests.Session()
    s.cookies.set("JWT_WEB", jwt_web, domain=".connect.garmin.com")
    s.cookies.set("GARMIN-SSO", "1", domain=".garmin.com")
    s.cookies.set("GARMIN-SSO-CUST-GUID", sso_guid, domain=".garmin.com")
    s.headers.update({
        "NK": "NT",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
    })

    # Profil testen
    r = s.get("https://connect.garmin.com/userprofile-service/socialProfile")
    if r.status_code == 200 and r.text.startswith("{"):
        data = r.json()
        return s, data.get("displayName", "Unknown")
    return None, None


def upload_tokens(jwt_web, sso_guid, skywalker_token):
    """Tokens ins Backend hochladen."""
    r = requests.post(
        f"{BACKEND_URL}/api/auth/garmin-browser-token",
        headers={"Authorization": f"Bearer {skywalker_token}"},
        json={"jwt_web": jwt_web, "sso_guid": sso_guid},
    )
    return r.status_code == 200, r.text


def main():
    print("=" * 60)
    print("Garmin Browser-Login für Skywalker")
    print("=" * 60)
    print()
    print("Ein Browser öffnet sich – logge dich dort bei Garmin ein.")
    print("Die App wartet bis du eingeloggt bist.")
    print()

    skywalker_token = get_skywalker_token()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=500)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        print("Browser öffnet sich...")
        page.goto("https://connect.garmin.com/signin")

        print("Bitte einloggen (CAPTCHA, MFA etc. normal durchführen)...")
        print("Warte auf erfolgreichen Login...")

        try:
            jwt_web, sso_guid = extract_oauth_tokens(page, context)
        except Exception as e:
            print(f"Timeout oder Fehler: {e}")
            browser.close()
            return

        browser.close()

    if not jwt_web:
        print("❌ Konnte keine Tokens extrahieren.")
        return

    print("\nTeste API-Verbindung...")
    session, display_name = test_garmin_api(jwt_web, sso_guid)

    if not session:
        print("❌ API-Test fehlgeschlagen – Tokens funktionieren nicht für direkte Calls.")
        print("   Tokens werden trotzdem gespeichert für späteren Versuch.")

    print(f"✓ Eingeloggt als: {display_name or 'Unbekannt'}")
    print("\nLade Tokens ins Backend hoch...")

    ok, msg = upload_tokens(jwt_web, sso_guid, skywalker_token)
    if ok:
        print("✓ Tokens erfolgreich gespeichert!")
        print("  Garmin Sync sollte jetzt funktionieren.")
    else:
        print(f"❌ Upload fehlgeschlagen: {msg}")
        # Lokal speichern als Fallback
        with open("/tmp/garmin_browser_tokens.json", "w") as f:
            json.dump({"jwt_web": jwt_web, "sso_guid": sso_guid}, f)
        print("  Tokens lokal gespeichert: /tmp/garmin_browser_tokens.json")


if __name__ == "__main__":
    main()
