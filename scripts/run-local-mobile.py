"""Run the isolated SQLite backend with verified approved model artifacts."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# The signed embeddable interpreter can reuse the project environment when
# Windows blocks its unsigned virtual-environment launcher.
if os.name == "nt" and Path(sys.prefix).resolve() != (ROOT / ".venv").resolve():
    import site

    site.addsitedir(str(ROOT / ".venv" / "Lib" / "site-packages"))

sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    # The embedded Windows interpreter needs its site directory first.
    from scripts.local_mobile_settings import load_local_mobile_settings

    os.chdir(ROOT)
    load_local_mobile_settings(ROOT)
    if os.environ.get("DEMO_ARTIFACT_INFERENCE_ENABLED") != "true":
        raise SystemExit("Local mobile testing requires actual approved artifacts.")
    (ROOT / "storage").mkdir(exist_ok=True)
    import uvicorn

    # Loopback only. BlueStacks uses adb reverse, without exposing the PC to the LAN.
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        reload_dirs=[str(ROOT / name) for name in ("app", "src", "ai_worker", "scripts")],
    )
