"""
Garmin Token via MFA-Login holen und auf Fly.io hochladen.
"""
import os
import subprocess
import getpass

TOKEN_DIR = os.path.expanduser("~/.garth_skywalker")

def login():
    import garth

    os.makedirs(TOKEN_DIR, exist_ok=True)

    email = input("Garmin Email: ").strip()
    password = getpass.getpass("Garmin Passwort: ").strip()

    def prompt_mfa():
        return input("MFA-Code (aus Email): ").strip()

    garth.configure()
    garth.login(email, password, prompt_mfa=prompt_mfa)
    garth.save(TOKEN_DIR)
    print(f"✅ Token gespeichert in {TOKEN_DIR}")
    return True


def upload():
    print("\nLade Token auf Fly.io hoch...")
    remote_dir = "/data/users/1/.garth"

    for fname in os.listdir(TOKEN_DIR):
        local_path = os.path.join(TOKEN_DIR, fname)
        with open(local_path, "r") as f:
            content = f.read()
        content_escaped = content.replace("\\", "\\\\").replace("'", "'\\''").replace("\n", "\\n")
        remote_cmd = f"mkdir -p {remote_dir} && printf '%b' '{content_escaped}' > {remote_dir}/{fname}"
        result = subprocess.run(
            ["fly", "ssh", "console", "--app", "mugnog", "-C", remote_cmd],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print(f"  ✅ {fname} hochgeladen")
        else:
            print(f"  ❌ {fname} Fehler: {result.stderr[:200]}")

    print("\n✅ Fertig! Garmin Sync in der App testen.")


if __name__ == "__main__":
    try:
        if login():
            upload()
    except Exception as e:
        print(f"❌ Fehler: {e}")
