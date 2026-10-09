"""Load local settings and inject a file-backed key into the server environment."""

import os
import re
from pathlib import Path

from dotenv import dotenv_values


def load_local_mobile_settings(root: Path) -> None:
    settings = dotenv_values(root / ".env.local-mobile")
    if not settings.get("SECRET_KEY"):
        raise SystemExit("Missing .env.local-mobile secret; run local setup first.")
    os.environ.update({key: value for key, value in settings.items() if value is not None})
    if os.environ.get("OPENAI_VLM_FALLBACK_ENABLED", "false").lower() != "true":
        return
    if not os.environ.get("OPENAI_API_KEY") and os.environ.get("OPENAI_API_KEY_FILE"):
        try:
            content = Path(os.environ["OPENAI_API_KEY_FILE"]).read_text(encoding="utf-8-sig")
            candidates = re.findall(r"sk-[A-Za-z0-9_-]+", content)
        except (OSError, UnicodeError):
            raise SystemExit("Cannot read the local OpenAI key file.") from None
        if len(candidates) != 1:
            raise SystemExit("The local OpenAI key file must contain exactly one API key.")
        os.environ["OPENAI_API_KEY"] = candidates[0]
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("VLM is enabled but the local OpenAI key is missing.")
