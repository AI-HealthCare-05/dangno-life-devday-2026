"""Create independent local settings without copying a user's database or secrets."""

import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def create_settings(destination: Path) -> bool:
    settings = {
        "ENV": "local",
        "SECRET_KEY": secrets.token_urlsafe(48),
        "DATABASE_URL": "sqlite://storage/local_mobile.sqlite3",
        "DB_GENERATE_SCHEMAS": "true",
        "DEMO_MODE": "true",
        "DEMO_ARTIFACT_INFERENCE_ENABLED": "true",
        "PREDICTION_PROVIDER": "artifact",
        "XAI_DISPLAY_ALLOWED": "true",
        "COOKIE_DOMAIN": "",
        "FRONTEND_BASE_URL": "http://127.0.0.1:8000",
    }
    try:
        with destination.open("x", encoding="utf-8") as output:
            output.write("# Private local settings; never commit or share this file.\n")
            output.writelines(f"{key}={value}\n" for key, value in settings.items())
    except FileExistsError:
        return False
    return True


if __name__ == "__main__":
    created = create_settings(ROOT / ".env.local-mobile")
    print("Created independent local settings." if created else "Existing local settings preserved.")
    print("Provision approved model files before starting scripts/run-local-mobile.py.")
